"""Validity predicates and membership ID generation.

Each rule from the brief is one small, independently testable
:class:`polars.Expr` that answers a single yes/no question.  :func:`predicates`
pairs each with the reason code reported when it fails, and is the single
source of truth from which both :func:`is_successful_expr` and
:func:`rejection_reason_expr` are derived -- so a rule can never be enforced
without being explainable, or explained without being enforced.

Null handling is deliberate throughout.  In Polars, ``null & True`` is ``null``,
and ``LazyFrame.filter`` drops null rows; an unguarded predicate would therefore
make malformed rows vanish from *both* output files.  Every predicate is
explicitly null-safe so that a row always lands in exactly one of them.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import operator

import polars as pl

from . import config
from .transform import ABOVE_18, BIRTHDAY_DATE, BIRTHDAY_YMD, FIRST_NAME, LAST_NAME, MOBILE_NORMALISED

logger = logging.getLogger(__name__)

#: Reason codes written to the ``rejection_reason`` column.
REASON_MISSING_NAME = "missing_name"
REASON_UNPARSEABLE_BIRTHDAY = "unparseable_birthday"
REASON_UNDER_18 = "under_18"
REASON_INVALID_MOBILE = "invalid_mobile"
REASON_INVALID_EMAIL = "invalid_email"

#: Columns added by :func:`validate`.
IS_SUCCESSFUL = "is_successful"
REJECTION_REASON = "rejection_reason"
MEMBERSHIP_ID = "membership_id"

#: Separator between reason codes when a row fails several rules.
REASON_SEPARATOR = ";"


# ---------------------------------------------------------------------------
# Predicates -- each returns True when the rule is satisfied
# ---------------------------------------------------------------------------


def has_name_expr() -> pl.Expr:
    """Whether the application carries a usable name.

    Tests ``first_name`` rather than the raw ``name`` column, so the rule
    catches every way a name can be absent with one comparison: ``null``, the
    empty string, whitespace only, or a bare salutation such as "Mr." that
    leaves nothing behind once stripped.

    Reads:
        ``first_name``

    Returns:
        A null-safe ``Boolean`` expression.
    """
    return pl.col(FIRST_NAME).is_not_null()


def parseable_birthday_expr() -> pl.Expr:
    """Whether the submitted birthday matched one of the accepted formats.

    Kept separate from :func:`is_adult_expr` so a data-quality problem (an
    unreadable date) is reported distinctly from a business rejection (a real
    date belonging to a minor).  Collapsing the two would make them
    indistinguishable in the audit file.

    Reads:
        ``birthday_date``

    Returns:
        A null-safe ``Boolean`` expression.
    """
    return pl.col(BIRTHDAY_DATE).is_not_null()


def is_adult_expr() -> pl.Expr:
    """Whether the applicant is over 18 as of the reference date.

    Abstains when the birthday did not parse: that row is already failed by
    :func:`parseable_birthday_expr`, and reporting ``under_18`` as well would
    assert an age we never managed to read.  The row still fails overall,
    because every predicate must pass for an application to succeed.

    Reads:
        ``birthday_date``, ``above_18``

    Returns:
        A null-safe ``Boolean`` expression.
    """
    return (
        pl.when(pl.col(BIRTHDAY_DATE).is_null())
        .then(pl.lit(True))
        .otherwise(pl.col(ABOVE_18))
        .fill_null(False)
    )


def valid_mobile_expr() -> pl.Expr:
    """Whether the mobile number is exactly 8 digits.

    Applied to the whitespace-stripped number, so ``6655 1251`` passes while
    ``123456789`` and ``6655-1251`` do not.

    Reads:
        ``mobile_normalised``

    Returns:
        A null-safe ``Boolean`` expression.
    """
    return pl.col(MOBILE_NORMALISED).str.contains(config.MOBILE_PATTERN).fill_null(False)


def valid_email_expr() -> pl.Expr:
    """Whether the email ends with one of the accepted suffixes.

    Case-insensitive and whitespace-tolerant.  The suffix list lives in
    :data:`config.ACCEPTED_EMAIL_SUFFIXES`; see the ASSUMPTION recorded there
    for why it is read at the top-level domain.

    Reads:
        ``email``

    Returns:
        A null-safe ``Boolean`` expression.
    """
    email = pl.col("email").str.strip_chars().str.to_lowercase()
    return functools.reduce(
        operator.or_,
        (email.str.ends_with(suffix) for suffix in config.ACCEPTED_EMAIL_SUFFIXES),
    ).fill_null(False)


def predicates() -> tuple[tuple[str, pl.Expr], ...]:
    """Every validity rule, paired with the reason reported when it fails.

    The order here is the order reason codes appear in ``rejection_reason``,
    so the column is stable and diffable across runs.

    Returns:
        Tuples of ``(reason_code, passes_expression)``.
    """
    return (
        (REASON_MISSING_NAME, has_name_expr()),
        (REASON_UNPARSEABLE_BIRTHDAY, parseable_birthday_expr()),
        (REASON_UNDER_18, is_adult_expr()),
        (REASON_INVALID_MOBILE, valid_mobile_expr()),
        (REASON_INVALID_EMAIL, valid_email_expr()),
    )


# ---------------------------------------------------------------------------
# Derived verdict columns
# ---------------------------------------------------------------------------


def is_successful_expr() -> pl.Expr:
    """Whether an application passes every validity rule.

    Returns:
        A null-safe ``Boolean`` expression -- the conjunction of every
        predicate in :func:`predicates`.
    """
    return functools.reduce(operator.and_, (passes for _, passes in predicates()))


def rejection_reason_expr() -> pl.Expr:
    """Every failed rule for a row, joined by ``;``.

    Reports *all* failures rather than short-circuiting on the first, so a
    reviewer can see everything wrong with an application in one pass instead
    of rediscovering it one fix at a time.  Built by collecting one nullable
    literal per rule into a list, dropping the nulls (the rules that passed)
    and joining what remains.

    Returns:
        A ``String`` expression; the empty string for a successful row.
    """
    return (
        pl.concat_list(
            *(
                pl.when(~passes).then(pl.lit(reason)).otherwise(None)
                for reason, passes in predicates()
            )
        )
        .list.drop_nulls()
        .list.join(REASON_SEPARATOR)
    )


def _sha256_prefix(value: str) -> str:
    """Hash a string with SHA-256 and keep the leading hex characters.

    Args:
        value: The ``YYYYMMDD`` birthday string.

    Returns:
        The first :data:`config.MEMBERSHIP_HASH_LENGTH` characters of the
        lower-case hex digest.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[: config.MEMBERSHIP_HASH_LENGTH]


def membership_hash_expr() -> pl.Expr:
    """Truncated SHA-256 of the formatted birthday.

    Polars has no native SHA-256 expression, so this maps the stdlib
    implementation over the column.  Nulls pass straight through without
    invoking the callable.

    Reads:
        ``birthday_ymd``

    Returns:
        A ``String`` expression; ``null`` where the birthday did not parse.
    """
    # ponytail: row-wise Python UDF, the one non-vectorised step in the graph.
    # Costs ~5k calls per batch here, which is nothing. If batches grow to
    # millions of rows, swap in the `polars-hash` plugin's native
    # `.chash.sha2_256()` -- same output, no Python round-trip.
    return pl.col(BIRTHDAY_YMD).map_elements(_sha256_prefix, return_dtype=pl.String)


def membership_id_expr() -> pl.Expr:
    """Membership ID for successful applications: ``<last_name>_<hash>``.

    Only successful applications get an ID; rejected rows keep ``null`` so the
    audit file cannot be mistaken for a source of valid memberships.

    Reads:
        ``last_name``, ``birthday_ymd``, plus everything :func:`predicates`
        reads.

    Returns:
        A ``String`` expression; ``null`` for unsuccessful applications.
    """
    return (
        pl.when(is_successful_expr())
        .then(pl.concat_str(pl.col(LAST_NAME), pl.lit("_"), membership_hash_expr()))
        .otherwise(None)
    )


def validate(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Add the verdict columns to a cleaned frame.

    Pure: the input frame is not mutated and nothing is materialised.  No rows
    are dropped here -- partitioning into successful and unsuccessful is
    :mod:`membership_pipeline.output`'s job, because that is where the results
    are written.

    Args:
        frame: Output of :func:`membership_pipeline.transform.clean`.

    Returns:
        A new ``LazyFrame`` with ``is_successful``, ``rejection_reason`` and
        ``membership_id`` added.
    """
    logger.debug("Building validation graph with %d predicate(s)", len(predicates()))
    return frame.with_columns(
        **{
            IS_SUCCESSFUL: is_successful_expr(),
            REJECTION_REASON: rejection_reason_expr(),
            MEMBERSHIP_ID: membership_id_expr(),
        }
    )

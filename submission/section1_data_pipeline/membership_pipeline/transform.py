"""Pure cleaning and formatting transformations.

Every public function here returns a :class:`polars.Expr` describing *how* to
compute a value, or a :class:`polars.LazyFrame` describing *how* to derive a
frame -- never a materialised result.  Nothing in this module reads a file,
mutates its input, or calls ``collect()``.

The expression builders read well-known column names (documented per function)
so they compose freely and can be unit-tested against a one-row frame.  Raw
source columns are never overwritten: derived fields are added alongside them,
so the unsuccessful-applications output can show both what arrived and what the
pipeline made of it.
"""

from __future__ import annotations

import logging
from datetime import date

import polars as pl

from . import config

logger = logging.getLogger(__name__)

#: Derived column names, referenced by :mod:`membership_pipeline.validate` and
#: :mod:`membership_pipeline.output`.
FIRST_NAME = "first_name"
LAST_NAME = "last_name"
BIRTHDAY_DATE = "birthday_date"
BIRTHDAY_YMD = "birthday_ymd"
AGE = "age"
ABOVE_18 = "above_18"
MOBILE_NORMALISED = "mobile_normalised"


# ---------------------------------------------------------------------------
# Name
# ---------------------------------------------------------------------------


def name_token_expr() -> pl.Expr:
    """Split ``name`` into whitespace-delimited tokens.

    Uses ``extract_all(r"\\S+")`` rather than ``split(" ")`` so that repeated
    spaces, tabs and leading/trailing whitespace cannot produce empty tokens.

    Reads:
        ``name``

    Returns:
        A ``List(String)`` expression; ``null`` where ``name`` is null, and an
        empty list where ``name`` is blank or whitespace only.
    """
    return pl.col("name").str.extract_all(r"\S+")


def core_name_token_expr() -> pl.Expr:
    """Drop a leading salutation and a trailing post-nominal suffix.

    "Mr. Larry Grimes MD" reduces to ``["Larry", "Grimes"]``.  Tokens are
    compared lower-cased with any trailing "." removed, so "Mr", "Mr." and
    "MR." all match.  A suffix is only stripped when more than one token
    remains, so an applicant recorded solely as "MD" keeps that as their name.

    Reads:
        ``name``

    Returns:
        A ``List(String)`` expression holding the name proper.  Possibly empty
        -- "Mr." on its own leaves nothing behind.
    """
    tokens = name_token_expr()
    first_normalised = tokens.list.first().str.to_lowercase().str.strip_chars_end(".")
    last_normalised = tokens.list.last().str.to_lowercase().str.strip_chars_end(".")

    offset = pl.when(first_normalised.is_in(list(config.SALUTATIONS))).then(1).otherwise(0)
    trailing = (
        pl.when((tokens.list.len() > 1) & last_normalised.is_in(list(config.NAME_SUFFIXES)))
        .then(1)
        .otherwise(0)
    )
    return tokens.list.slice(offset, tokens.list.len() - offset - trailing)


def first_name_expr() -> pl.Expr:
    """First token of the name proper.

    Reads:
        ``name``

    Returns:
        A ``String`` expression; ``null`` when no name survives salutation and
        suffix stripping.
    """
    core = core_name_token_expr()
    return pl.when(core.list.len() >= 1).then(core.list.first()).otherwise(None)


def last_name_expr() -> pl.Expr:
    """Everything after the first token of the name proper, space-joined.

    Middle names are kept with the surname ("Mary Ann Smith" -> "Ann Smith")
    rather than discarded, so no part of the submitted name is silently lost.

    A mononym ("Cher") yields an empty string, not ``null``: the applicant did
    provide a name, they simply have no surname, and an empty string keeps them
    eligible.  ``null`` is reserved for "there is no name here at all".

    Reads:
        ``name``

    Returns:
        A ``String`` expression.
    """
    core = core_name_token_expr()
    length = core.list.len()
    return (
        pl.when(length >= 2)
        .then(core.list.slice(1).list.join(" "))
        .when(length == 1)
        .then(pl.lit(""))
        .otherwise(None)
    )


# ---------------------------------------------------------------------------
# Birthday
# ---------------------------------------------------------------------------


def birthday_date_expr() -> pl.Expr:
    """Parse ``birthday`` into a ``Date`` by trying each accepted format.

    ``pl.coalesce`` takes the first format that parses; every attempt uses
    ``strict=False`` so an unparseable value becomes ``null`` instead of
    raising.  Impossible dates such as ``1996/02/31`` therefore fall through
    every format and surface as a rejection, not a crash.

    Reads:
        ``birthday``

    Returns:
        A ``Date`` expression; ``null`` when no format matches.
    """
    trimmed = pl.col("birthday").str.strip_chars()
    return pl.coalesce(
        [trimmed.str.to_date(fmt, strict=False) for fmt in config.BIRTHDAY_INPUT_FORMATS]
    )


def birthday_ymd_expr() -> pl.Expr:
    """Format the parsed birthday as the ``YYYYMMDD`` string the brief requires.

    Reads:
        ``birthday_date`` (from :func:`birthday_date_expr`)

    Returns:
        A ``String`` expression; ``null`` where the birthday did not parse.
    """
    return pl.col(BIRTHDAY_DATE).dt.strftime(config.BIRTHDAY_OUTPUT_FORMAT)


def age_expr(reference: date = config.REFERENCE_DATE) -> pl.Expr:
    """Whole years completed as of ``reference``.

    Computed by calendar comparison rather than dividing a day count, so it is
    exact on leap days: someone born 2004-02-29 is 17 on 2022-01-01, because
    their birthday has not yet come round in 2022.

    Args:
        reference: Date the age is assessed on.  Defaults to 1 January 2022 per
            the brief, but is a parameter so tests -- and any future change of
            policy -- need not patch a global.

    Reads:
        ``birthday_date`` (from :func:`birthday_date_expr`)

    Returns:
        An ``Int32`` expression; ``null`` where the birthday did not parse.
    """
    birthday = pl.col(BIRTHDAY_DATE)
    month, day = birthday.dt.month(), birthday.dt.day()
    birthday_has_passed = (month < reference.month) | (
        (month == reference.month) & (day <= reference.day)
    )
    return (
        (pl.lit(reference.year) - birthday.dt.year()) - (~birthday_has_passed).cast(pl.Int32)
    ).cast(pl.Int32)


def above_18_expr(reference: date = config.REFERENCE_DATE) -> pl.Expr:
    """Whether the applicant is over 18 as of ``reference``.

    Strictly greater than :data:`config.MIN_AGE`: an applicant who turns 18 on
    the reference date does not qualify.

    Args:
        reference: Date the age is assessed on.

    Reads:
        ``birthday_date`` (from :func:`birthday_date_expr`)

    Returns:
        A ``Boolean`` expression; ``null`` where the birthday did not parse.
        :mod:`membership_pipeline.validate` is responsible for treating that
        ``null`` as a failure.
    """
    return age_expr(reference) > config.MIN_AGE


# ---------------------------------------------------------------------------
# Mobile
# ---------------------------------------------------------------------------


def normalised_mobile_expr() -> pl.Expr:
    """Strip whitespace from ``mobile`` so formatting cannot fail validation.

    304 of the 4,999 sample rows are written as e.g. ``6655 1251``.  The space
    is presentation, not data, so it is removed before the 8-digit check.  The
    raw ``mobile`` column is left untouched for the audit trail.

    Reads:
        ``mobile``

    Returns:
        A ``String`` expression; ``null`` where ``mobile`` is null.
    """
    return pl.col("mobile").str.replace_all(config.MOBILE_WHITESPACE_PATTERN, "")


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def clean(frame: pl.LazyFrame, reference: date = config.REFERENCE_DATE) -> pl.LazyFrame:
    """Add every derived field to a scanned batch frame.

    Pure: the input frame is not mutated and nothing is read from disk.  Two
    ``with_columns`` stages are needed because ``birthday_ymd``, ``age`` and
    ``above_18`` are all defined in terms of the ``birthday_date`` produced by
    the first stage.

    Args:
        frame: Output of :func:`membership_pipeline.ingest.scan_batches`.
        reference: Date ages are assessed on.

    Returns:
        A new ``LazyFrame`` carrying the original columns plus ``first_name``,
        ``last_name``, ``birthday_date``, ``birthday_ymd``, ``age``,
        ``above_18`` and ``mobile_normalised``.
    """
    logger.debug("Building cleaning graph with reference date %s", reference)
    return frame.with_columns(
        **{
            FIRST_NAME: first_name_expr(),
            LAST_NAME: last_name_expr(),
            BIRTHDAY_DATE: birthday_date_expr(),
            MOBILE_NORMALISED: normalised_mobile_expr(),
        }
    ).with_columns(
        **{
            BIRTHDAY_YMD: birthday_ymd_expr(),
            AGE: age_expr(reference),
            ABOVE_18: above_18_expr(reference),
        }
    )

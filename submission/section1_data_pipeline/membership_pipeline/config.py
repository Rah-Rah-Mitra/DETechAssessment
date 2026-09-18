"""Configuration constants for the membership application pipeline.

This module is the single source of truth for every business rule, schema and
naming convention the pipeline applies.  It deliberately contains **no logic**:
a reviewer should be able to read this one file and know exactly which
assumptions the pipeline encodes, without tracing them through expressions.

Assumptions encoded here that are *interpretations* of the brief rather than
literal readings are marked with ``ASSUMPTION``; each is repeated in the
section ``README.md``.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from typing import Final

import polars as pl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source schema
# ---------------------------------------------------------------------------

#: Columns required in every incoming batch CSV.
#:
#: Everything is read as ``pl.String``.  Reading dates or phone numbers as
#: typed columns would let a single malformed cell abort the whole scan; by
#: ingesting raw text and parsing with ``strict=False`` downstream, a bad value
#: degrades to ``null`` and is reported as a rejection instead of an exception.
SOURCE_SCHEMA: Final[dict[str, type[pl.DataType]]] = {
    "name": pl.String,
    "email": pl.String,
    "date_of_birth": pl.String,
    "mobile_no": pl.String,
}

#: Source column name -> canonical name used throughout the pipeline.
#:
#: ASSUMPTION: the brief refers to ``birthday`` and ``mobile``; the delivered
#: datasets use ``date_of_birth`` and ``mobile_no``.  They are the same fields,
#: so we rename once at the ingestion boundary and speak the brief's vocabulary
#: everywhere after that.
COLUMN_ALIASES: Final[dict[str, str]] = {
    "name": "name",
    "email": "email",
    "date_of_birth": "birthday",
    "mobile_no": "mobile",
}

#: Synthetic column added at scan time recording which batch file a row came
#: from, so a rejected row can always be traced back to its source.
SOURCE_FILE_COLUMN: Final[str] = "source_file"

#: Glob used to discover batch files in the input folder.
BATCH_GLOB: Final[str] = "*.csv"


# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------

#: Age is assessed as of this date, per the brief ("over 18 years old as of
#: 1 Jan 2022").  Injected as a parameter everywhere so tests can vary it.
REFERENCE_DATE: Final[date] = date(2022, 1, 1)

#: ASSUMPTION: "over 18" is read as strictly greater than 18, i.e. ``age > 18``.
#: An applicant who is exactly 18 on the reference date does not qualify.
MIN_AGE: Final[int] = 18

#: Birthday formats accepted on input, tried in order via ``pl.coalesce``.
#:
#: ASSUMPTION: the separator disambiguates day-first from month-first.  Across
#: the 4,999 sample rows, 760 slash-dates have a second component > 12 (and
#: none have a first component > 12), while 735 dash-dates have a first
#: component > 12 (and none have a second component > 12).  There is not a
#: single counter-example, so ``/`` means ``MM/DD/YYYY`` and ``-`` means
#: ``DD-MM-YYYY``.  Anything else parses to ``null`` and is rejected rather
#: than silently guessed.
BIRTHDAY_INPUT_FORMATS: Final[tuple[str, ...]] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d-%m-%Y",
)

#: Output format for the ``birthday`` field, per the brief.
BIRTHDAY_OUTPUT_FORMAT: Final[str] = "%Y%m%d"

#: ASSUMPTION: the brief's ``@emailprovider.com`` / ``@emailprovider.net`` is a
#: placeholder for "the membership provider's domain", not a literal domain --
#: no row in either delivered dataset uses it, so the literal reading yields
#: zero successful applications.  The rule is therefore applied at the
#: top-level-domain: an email is valid if it ends with one of these suffixes.
#: Matching is case-insensitive.
ACCEPTED_EMAIL_SUFFIXES: Final[tuple[str, ...]] = (".com", ".net")

#: A mobile number is valid if it is exactly 8 digits.
MOBILE_PATTERN: Final[str] = r"^\d{8}$"

#: ASSUMPTION: whitespace inside a mobile number is formatting, not data.
#: 304 sample rows are written as e.g. ``6655 1251``; these are stripped to
#: ``66551251`` before the pattern above is applied.
MOBILE_WHITESPACE_PATTERN: Final[str] = r"\s+"

#: Number of leading hex characters of the SHA-256 digest used in a
#: membership ID (``<last_name>_<hash(YYYYMMDD)>``).
MEMBERSHIP_HASH_LENGTH: Final[int] = 5

#: Honorifics stripped from the front of a name before splitting.  Compared
#: lower-cased with any trailing "." removed, so "Mr", "Mr." and "MR." all match.
SALUTATIONS: Final[frozenset[str]] = frozenset(
    {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "rev", "sir", "madam"}
)

#: Post-nominal suffixes stripped from the end of a name before splitting.
#: Normalised the same way as SALUTATIONS.
NAME_SUFFIXES: Final[frozenset[str]] = frozenset(
    {"jr", "sr", "ii", "iii", "iv", "v", "md", "dds", "dvm", "phd", "esq", "do", "rn"}
)


# ---------------------------------------------------------------------------
# Output layout
# ---------------------------------------------------------------------------

SUCCESSFUL_DIR_NAME: Final[str] = "successful"
UNSUCCESSFUL_DIR_NAME: Final[str] = "unsuccessful"

#: Timestamp format shared by output filenames and archive folder names, so
#: every artefact of a single run is obviously related.
RUN_TIMESTAMP_FORMAT: Final[str] = "%Y%m%d_%H%M%S"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging for a pipeline run.

    Called once from the CLI entry point.  Library modules only ever call
    ``logging.getLogger(__name__)`` and never configure handlers themselves, so
    importing this package from a notebook or from Airflow does not hijack the
    host application's logging setup.

    Args:
        level: Any name accepted by ``logging.getLevelName``, e.g. ``"DEBUG"``.
    """
    logging.basicConfig(
        level=level.upper(),
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )

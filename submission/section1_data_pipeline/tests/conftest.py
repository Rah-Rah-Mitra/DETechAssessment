"""Shared test fixtures and helpers.

Keeps the section root on ``sys.path`` so the tests run the same way whether
invoked as ``pytest``, ``pytest tests/`` or ``python -m pytest`` from anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

SECTION_ROOT = Path(__file__).resolve().parent.parent
if str(SECTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SECTION_ROOT))

from membership_pipeline import transform, validate  # noqa: E402

#: The columns ingest.scan_batches() guarantees, with their guaranteed dtype.
#: Declared explicitly because an all-None literal would otherwise infer dtype
#: Null and fail on the string operations the pipeline applies.
SOURCE_SCHEMA = {
    "name": pl.String,
    "email": pl.String,
    "birthday": pl.String,
    "mobile": pl.String,
}


def source_frame(**columns: list) -> pl.LazyFrame:
    """Build a frame shaped like the output of ``ingest.scan_batches``.

    Columns not supplied are filled with nulls, so a test can name only the
    field it cares about.

    Args:
        **columns: Column name to list of values.

    Returns:
        A ``LazyFrame`` with the full source schema.
    """
    height = max(len(values) for values in columns.values())
    data = {name: list(columns.get(name, [None] * height)) for name in SOURCE_SCHEMA}
    return pl.LazyFrame(data, schema=SOURCE_SCHEMA)


def cleaned(**columns: list) -> pl.DataFrame:
    """Run the cleaning stage over a literal fixture."""
    return transform.clean(source_frame(**columns)).collect()


def validated(**columns: list) -> pl.DataFrame:
    """Run the cleaning and validation stages over a literal fixture."""
    return validate.validate(transform.clean(source_frame(**columns))).collect()

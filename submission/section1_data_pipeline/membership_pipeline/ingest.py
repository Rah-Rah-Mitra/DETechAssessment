"""Batch discovery and lazy CSV ingestion.

The ingestion boundary is the one place the pipeline touches the outside world
on the way in.  Its job is narrow: find the batch files, describe how to read
them, and hand back a :class:`polars.LazyFrame` with a known schema and
canonical column names.  No cleaning, no filtering, no ``collect()``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import polars as pl

from . import config

logger = logging.getLogger(__name__)


class MissingColumnsError(ValueError):
    """Raised when a batch file does not contain the required source columns."""


def discover_batches(input_dir: Path | str) -> list[Path]:
    """Find the CSV batches waiting in ``input_dir``.

    Args:
        input_dir: Folder the hourly batches are dropped into.

    Returns:
        Batch paths sorted by name, so a run's file order is deterministic and
        re-running the same input produces byte-identical output.  An empty
        list when there is nothing to process -- that is a normal state for an
        hourly schedule, not an error.

    Raises:
        NotADirectoryError: If ``input_dir`` does not exist or is not a folder.
    """
    directory = Path(input_dir)
    if not directory.is_dir():
        raise NotADirectoryError(f"Input directory does not exist: {directory}")

    files = sorted(directory.glob(config.BATCH_GLOB))
    logger.info("Discovered %d batch file(s) in %s", len(files), directory)
    for file in files:
        logger.debug("  batch: %s", file.name)
    return files


def scan_batches(files: Sequence[Path | str]) -> pl.LazyFrame:
    """Build a lazy scan over every batch file, with a strict source schema.

    All four source fields are read as ``pl.String``.  Deferring date and phone
    parsing to the transformation stage means a malformed cell becomes a
    ``null`` we can report on, rather than an exception that loses the whole
    batch.

    Columns are renamed to the canonical vocabulary (``date_of_birth`` ->
    ``birthday``, ``mobile_no`` -> ``mobile``) and selected **by name**, so a
    batch whose columns arrive in a different order, or which carries extra
    columns, is still read correctly.

    Args:
        files: Batch paths, typically from :func:`discover_batches`.

    Returns:
        A ``LazyFrame`` with columns ``name``, ``email``, ``birthday``,
        ``mobile`` and ``source_file`` -- all ``String``.  Nothing has been
        read from disk yet beyond the headers.

    Raises:
        ValueError: If ``files`` is empty.
        MissingColumnsError: If any required source column is absent.
    """
    if not files:
        raise ValueError("scan_batches() requires at least one file; check discover_batches() first")

    paths = [str(Path(file)) for file in files]
    frame = pl.scan_csv(
        paths,
        schema_overrides=config.SOURCE_SCHEMA,
        include_file_paths=config.SOURCE_FILE_COLUMN,
        has_header=True,
    )

    _assert_required_columns(frame)

    canonical = frame.select(
        *(pl.col(source).alias(target) for source, target in config.COLUMN_ALIASES.items()),
        pl.col(config.SOURCE_FILE_COLUMN),
    )
    logger.info("Scanning %d file(s); schema: %s", len(paths), dict(canonical.collect_schema()))
    return canonical


def _assert_required_columns(frame: pl.LazyFrame) -> None:
    """Fail fast if the scanned frame is missing a required source column.

    ``schema_overrides`` only *types* the columns it names; it does not require
    them to exist, so a truncated or wrong-format file would otherwise surface
    much later as a confusing expression error.  Resolving the schema reads
    only the CSV headers, not the data.

    Args:
        frame: The freshly scanned, not-yet-renamed frame.

    Raises:
        MissingColumnsError: If any key of ``config.SOURCE_SCHEMA`` is absent.
    """
    present = set(frame.collect_schema().names())
    missing = [column for column in config.SOURCE_SCHEMA if column not in present]
    if missing:
        raise MissingColumnsError(
            f"Batch files are missing required column(s): {', '.join(missing)}. "
            f"Found: {', '.join(sorted(present))}"
        )

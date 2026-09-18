"""Materialisation, partitioning and archival.

This is the **only** module in the package that executes a query graph or
touches the filesystem on the way out.  Everything upstream builds a lazy plan;
:func:`write_outputs` is where that plan finally runs.

Keeping materialisation in one place means the rest of the pipeline can be
imported, composed and unit-tested without writing a byte to disk.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import polars as pl

from . import config
from .transform import ABOVE_18, AGE, BIRTHDAY_YMD, FIRST_NAME, LAST_NAME, MOBILE_NORMALISED
from .validate import IS_SUCCESSFUL, MEMBERSHIP_ID, REJECTION_REASON

logger = logging.getLogger(__name__)


def _successful_projection() -> list[pl.Expr]:
    """Columns written for a successful application, in the order the brief lists.

    ``birthday`` is the formatted ``YYYYMMDD`` string and ``mobile`` is the
    whitespace-stripped number -- downstream engineers receive the cleaned
    values, not the raw submissions.
    """
    return [
        pl.col(MEMBERSHIP_ID),
        pl.col(FIRST_NAME),
        pl.col(LAST_NAME),
        pl.col("email"),
        pl.col(BIRTHDAY_YMD).alias("birthday"),
        pl.col(ABOVE_18),
        pl.col(MOBILE_NORMALISED).alias("mobile"),
    ]


def _unsuccessful_projection() -> list[pl.Expr]:
    """Columns written for a rejected application.

    Carries the raw submission *and* what the pipeline derived from it, so an
    auditor can see both what the applicant typed and how it was interpreted,
    plus which batch file it arrived in.  ``rejection_reason`` lists every rule
    the row failed.
    """
    return [
        pl.col("name"),
        pl.col("email"),
        pl.col("birthday").alias("birthday_raw"),
        pl.col("mobile").alias("mobile_raw"),
        pl.col(FIRST_NAME),
        pl.col(LAST_NAME),
        pl.col(BIRTHDAY_YMD).alias("birthday"),
        pl.col(AGE),
        pl.col(ABOVE_18),
        pl.col(REJECTION_REASON),
        pl.col(config.SOURCE_FILE_COLUMN),
    ]


@dataclass(frozen=True)
class RunSummary:
    """Outcome of one pipeline run.

    Immutable, and convertible to plain JSON-safe types via :meth:`to_dict` so
    it can travel through an Airflow XCom.

    Attributes:
        run_ts: The single timestamp shared by every artefact of this run.
        files: Number of batch files processed.
        rows_in: Total rows read across those files.
        successful: Rows that passed every validity rule.
        unsuccessful: Rows that failed at least one.
        output_paths: Written CSVs, keyed ``successful`` / ``unsuccessful``.
        archived: Batch files moved into the archive.
    """

    run_ts: datetime
    files: int = 0
    rows_in: int = 0
    successful: int = 0
    unsuccessful: int = 0
    output_paths: dict[str, Path] = field(default_factory=dict)
    archived: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Render as JSON-serialisable primitives for XCom or structured logs."""
        return {
            "run_ts": self.run_ts.isoformat(),
            "files": self.files,
            "rows_in": self.rows_in,
            "successful": self.successful,
            "unsuccessful": self.unsuccessful,
            "output_paths": {key: str(path) for key, path in self.output_paths.items()},
            "archived": [str(path) for path in self.archived],
        }

    def log_line(self) -> str:
        """One-line, grep-friendly rendering for the run summary log entry.

        Path keys are suffixed ``_path`` so no key appears twice on the line and
        a log scraper can split it on whitespace and ``=`` unambiguously.
        """
        paths = " ".join(f"{key}_path={path}" for key, path in self.output_paths.items())
        return (
            f"files={self.files} rows_in={self.rows_in} "
            f"successful={self.successful} unsuccessful={self.unsuccessful} "
            f"archived={len(self.archived)} {paths}".strip()
        )


def write_outputs(
    frame: pl.LazyFrame,
    output_dir: Path | str,
    run_ts: datetime | None = None,
) -> RunSummary:
    """Execute the pipeline graph and write the two result files.

    The run timestamp is resolved **once** here and threaded through every
    filename, so all artefacts of a run share a stamp.  A scheduler can pass its
    logical run time instead, making a re-run of the same interval overwrite the
    same files rather than accumulating duplicates.

    Args:
        frame: Output of :func:`membership_pipeline.validate.validate`.
        output_dir: Root folder; ``successful/`` and ``unsuccessful/``
            subfolders are created beneath it.
        run_ts: Timestamp for this run.  Defaults to ``datetime.now()``.

    Returns:
        A :class:`RunSummary` with the row counts and written paths.
    """
    run_ts = run_ts or datetime.now()
    stamp = run_ts.strftime(config.RUN_TIMESTAMP_FORMAT)
    root = Path(output_dir)

    # ponytail: one collect() then two in-memory filters, rather than two
    # sink_csv() calls. Two sinks would scan the input batches twice and still
    # not give us the row counts the run summary has to report. The ceiling is
    # memory: an hourly batch is thousands of rows, not billions. If batches
    # ever outgrow RAM, switch to sink_csv and count with a separate
    # select(pl.len()) pass.
    frame_df = frame.collect()
    rows_in = frame_df.height

    successful = frame_df.filter(pl.col(IS_SUCCESSFUL)).select(_successful_projection())
    unsuccessful = frame_df.filter(~pl.col(IS_SUCCESSFUL)).select(_unsuccessful_projection())

    paths = {
        "successful": _write_csv(
            successful, root / config.SUCCESSFUL_DIR_NAME, f"successful_applications_{stamp}.csv"
        ),
        "unsuccessful": _write_csv(
            unsuccessful,
            root / config.UNSUCCESSFUL_DIR_NAME,
            f"unsuccessful_applications_{stamp}.csv",
        ),
    }

    return RunSummary(
        run_ts=run_ts,
        rows_in=rows_in,
        successful=successful.height,
        unsuccessful=unsuccessful.height,
        output_paths=paths,
    )


def _write_csv(frame: pl.DataFrame, directory: Path, filename: str) -> Path:
    """Write a frame to ``directory/filename``, creating the folder if needed.

    Args:
        frame: Already-materialised results.
        directory: Destination folder.
        filename: Timestamped file name.

    Returns:
        The path written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    frame.write_csv(destination)
    logger.info("Wrote %d row(s) to %s", frame.height, destination)
    return destination


def archive_batches(
    files: Sequence[Path | str],
    archive_dir: Path | str,
    run_ts: datetime,
) -> list[Path]:
    """Move processed batch files into ``archive_dir/<run_ts>/``.

    Archival is what makes the hourly schedule safe to repeat: once a batch has
    been processed it leaves the input folder, so the next run cannot pick it up
    again and double-count its applications.

    Args:
        files: The batch files that were processed.
        archive_dir: Archive root.
        run_ts: The same timestamp used for the output filenames, so a run's
            inputs and outputs can be matched up after the fact.

    Returns:
        The new location of each moved file; empty when there was nothing to do.
    """
    if not files:
        logger.info("No batch files to archive")
        return []

    destination_dir = Path(archive_dir) / run_ts.strftime(config.RUN_TIMESTAMP_FORMAT)
    destination_dir.mkdir(parents=True, exist_ok=True)

    moved: list[Path] = []
    for file in files:
        source = Path(file)
        destination = _unique_destination(destination_dir / source.name)
        shutil.move(str(source), str(destination))
        logger.debug("Archived %s -> %s", source.name, destination)
        moved.append(destination)

    logger.info("Archived %d batch file(s) to %s", len(moved), destination_dir)
    return moved


def _unique_destination(destination: Path) -> Path:
    """Return ``destination``, or the first free ``name_1.csv``-style variant.

    A scheduler replaying an interval passes the same ``logical_date``, so a
    backfill can legitimately target an archive folder that already holds a
    file of the same name.  ``shutil.move`` onto an existing path is an error on
    Windows and a silent overwrite on POSIX; neither is acceptable for an audit
    trail, so we step aside instead.

    Args:
        destination: The preferred path.

    Returns:
        A path that does not yet exist.
    """
    if not destination.exists():
        return destination

    for index in range(1, 1000):
        candidate = destination.with_name(f"{destination.stem}_{index}{destination.suffix}")
        if not candidate.exists():
            logger.warning("%s already archived; storing as %s", destination.name, candidate.name)
            return candidate

    raise FileExistsError(f"Cannot find a free archive name for {destination}")

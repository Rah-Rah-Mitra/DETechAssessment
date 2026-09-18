"""Command-line entry point: ``python -m membership_pipeline``.

Wires the five stages together -- ingest, transform, validate, output, archive --
and translates the outcome into a process exit code a scheduler can alert on.

:func:`run` is the importable form of the same pipeline; the Airflow DAG in
``scheduler/airflow_dag.py`` calls it directly so that cron and Airflow execute
identical code.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from . import config, ingest, output, transform, validate

logger = logging.getLogger(__name__)

DEFAULT_INPUT_DIR = "./input_batches"
DEFAULT_OUTPUT_DIR = "./output"
DEFAULT_ARCHIVE_DIR = "./archive"


def run(
    input_dir: Path | str = DEFAULT_INPUT_DIR,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    archive_dir: Path | str = DEFAULT_ARCHIVE_DIR,
    archive: bool = True,
    run_ts: datetime | None = None,
    reference: date = config.REFERENCE_DATE,
) -> output.RunSummary:
    """Run the pipeline once over whatever batches are waiting.

    An empty input folder is a normal outcome for an hourly schedule, not a
    failure: it is logged and reported as a zero-row run.

    Archival happens only after the outputs are safely written, so a failure
    mid-run leaves the input batches untouched and the run can simply be
    repeated.

    Args:
        input_dir: Folder the hourly batches are dropped into.
        output_dir: Root for the ``successful/`` and ``unsuccessful/`` results.
        archive_dir: Root for processed-batch archival.
        archive: Whether to move processed batches into the archive.
        run_ts: Timestamp shared by every artefact of this run.  Defaults to
            ``datetime.now()``; a scheduler should pass its logical run time.
        reference: Date ages are assessed on.

    Returns:
        A :class:`membership_pipeline.output.RunSummary`.
    """
    run_ts = run_ts or datetime.now()
    files = ingest.discover_batches(input_dir)

    if not files:
        logger.info("No batch files in %s; nothing to do", input_dir)
        return output.RunSummary(run_ts=run_ts)

    frame = validate.validate(transform.clean(ingest.scan_batches(files), reference))
    summary = output.write_outputs(frame, output_dir, run_ts=run_ts)

    archived = output.archive_batches(files, archive_dir, run_ts) if archive else []
    if not archive:
        logger.warning("Archiving disabled; %d batch file(s) remain in %s", len(files), input_dir)

    return output.RunSummary(
        run_ts=summary.run_ts,
        files=len(files),
        rows_in=summary.rows_in,
        successful=summary.successful,
        unsuccessful=summary.unsuccessful,
        output_paths=summary.output_paths,
        archived=archived,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="python -m membership_pipeline",
        description="Process hourly batches of membership applications.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_DIR, help="Folder holding batch CSVs")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="Root folder for results")
    parser.add_argument("--archive", default=DEFAULT_ARCHIVE_DIR, help="Root folder for processed batches")
    parser.add_argument(
        "--no-archive",
        dest="should_archive",
        action="store_false",
        help="Leave batches in the input folder (they will be reprocessed next run)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success -- including a run that found no batches -- and ``1``
        on any unhandled failure, so cron and Airflow can alert on it.
    """
    args = build_parser().parse_args(argv)
    config.configure_logging(args.log_level)

    try:
        summary = run(
            input_dir=args.input,
            output_dir=args.output,
            archive_dir=args.archive,
            archive=args.should_archive,
        )
    except Exception:
        logger.exception("Pipeline run failed")
        return 1

    logger.info("Run summary | %s", summary.log_line())
    return 0


if __name__ == "__main__":
    sys.exit(main())

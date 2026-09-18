"""Airflow DAG running the membership pipeline every hour.

Deploy by copying (or symlinking) this file into ``$AIRFLOW_HOME/dags/`` with
the ``membership_pipeline`` package importable -- e.g. ``pip install -e`` the
section root, or add it to ``PYTHONPATH``.

The DAG calls :func:`membership_pipeline.__main__.run` directly rather than
shelling out, so Airflow and cron execute exactly the same code path and a
failure surfaces as a Python traceback in the task log instead of an opaque
exit code.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pendulum
from airflow import DAG

# Airflow 2.x import path. On Airflow 3.x these live in
# `airflow.providers.standard.operators.python`.
from airflow.operators.python import PythonOperator, ShortCircuitOperator

from membership_pipeline import ingest
from membership_pipeline.__main__ import run

#: Section root; override with PIPELINE_HOME when deploying elsewhere.
PIPELINE_HOME = Path(os.environ.get("PIPELINE_HOME", Path(__file__).resolve().parent.parent))

INPUT_DIR = PIPELINE_HOME / "input_batches"
OUTPUT_DIR = PIPELINE_HOME / "output"
ARCHIVE_DIR = PIPELINE_HOME / "archive"

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
}


def check_for_files() -> bool:
    """Short-circuit the run when no batches are waiting.

    An idle hour is normal, not an error.  Returning ``False`` skips the
    downstream tasks and leaves the DAG run green, so the alerting channel stays
    meaningful.

    Returns:
        ``True`` when at least one batch file is present.
    """
    files = ingest.discover_batches(INPUT_DIR)
    print(f"Found {len(files)} batch file(s) in {INPUT_DIR}")
    return bool(files)


def process_applications(logical_date: datetime, **_: Any) -> dict[str, Any]:
    """Run the pipeline for one scheduled interval.

    Airflow's ``logical_date`` is passed through as the run timestamp, so a
    replayed interval reproduces the same output filenames and archive folder
    instead of creating a second set. The return value becomes this task's XCom.

    Args:
        logical_date: The interval this DAG run represents, injected by Airflow.

    Returns:
        The run summary as JSON-safe primitives.
    """
    summary = run(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        archive_dir=ARCHIVE_DIR,
        run_ts=logical_date,
    )
    return summary.to_dict()


def publish_summary(ti: Any, **_: Any) -> None:
    """Emit the run summary for downstream consumers and alerting.

    Reads the upstream task's XCom.  This is the seam where a real deployment
    would post to Slack, write to a metrics backend, or notify the downstream
    engineers that a new successful-applications file is ready.

    Args:
        ti: The task instance, injected by Airflow.
    """
    summary = ti.xcom_pull(task_ids="process_applications")
    print(
        "Membership pipeline run complete | "
        f"files={summary['files']} rows_in={summary['rows_in']} "
        f"successful={summary['successful']} unsuccessful={summary['unsuccessful']}"
    )
    for label, path in summary["output_paths"].items():
        print(f"  {label}: {path}")


with DAG(
    dag_id="membership_applications_hourly",
    description="Ingest, validate and consolidate hourly membership applications",
    schedule="@hourly",
    start_date=pendulum.datetime(2022, 1, 1, tz="UTC"),
    # Do not replay every hour since the start date on first deploy.
    catchup=False,
    # One run at a time: concurrent runs would race over the same input folder
    # and could archive a batch another run is still reading.
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["membership", "hourly", "polars"],
) as dag:
    check = ShortCircuitOperator(
        task_id="check_for_files",
        python_callable=check_for_files,
    )

    process = PythonOperator(
        task_id="process_applications",
        python_callable=process_applications,
    )

    publish = PythonOperator(
        task_id="publish_summary",
        python_callable=publish_summary,
    )

    check >> process >> publish

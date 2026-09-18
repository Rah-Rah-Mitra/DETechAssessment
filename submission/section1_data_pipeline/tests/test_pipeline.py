"""End-to-end tests: the CLI over a temporary folder of batch files."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from membership_pipeline.__main__ import main, run

RUN_TS = datetime(2022, 3, 1, 9, 0, 0)
STAMP = "20220301_090000"

#: Two batches, five applications, two of which should succeed.
BATCH_A = """name,email,date_of_birth,mobile_no
Mr. William Dixon,William_Dixon@provider.com,1986/01/10,4060 1711
Kristen Horn,Kristen_Horn@lin.com,1974-09-10,737931
Cathy Werner,Cathy_Werner@martinez.net,2018-09-25,71380411
"""

BATCH_B = """name,email,date_of_birth,mobile_no
Sherry Gonzalez DDS,Sherry_Gonzalez@caldwell.net,14-03-1973,66744895
,Nobody_Here@jackson.com,1990-01-01,12345678
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A throwaway pipeline home seeded with two batch files."""
    batches = tmp_path / "input_batches"
    batches.mkdir()
    (batches / "applications_batch_a.csv").write_text(BATCH_A, encoding="utf-8")
    (batches / "applications_batch_b.csv").write_text(BATCH_B, encoding="utf-8")
    return tmp_path


def read_output(workspace: Path, kind: str) -> pl.DataFrame:
    """Read a written result file back, keeping every column as text.

    ``infer_schema=False`` mirrors how a downstream consumer should read these
    files: ``birthday`` and ``mobile`` are digit strings, and type inference
    would turn them into integers and strip any leading zero.
    """
    (path,) = (workspace / "output" / kind).glob("*.csv")
    return pl.read_csv(path, infer_schema=False)


def test_run_produces_the_expected_partition(workspace: Path) -> None:
    summary = run(
        workspace / "input_batches",
        workspace / "output",
        workspace / "archive",
        run_ts=RUN_TS,
    )

    assert summary.files == 2
    assert summary.rows_in == 5
    assert summary.successful == 2
    assert summary.unsuccessful == 3
    assert summary.successful + summary.unsuccessful == summary.rows_in

    successful = read_output(workspace, "successful")
    unsuccessful = read_output(workspace, "unsuccessful")
    assert successful.height == 2
    assert unsuccessful.height == 3


def test_run_writes_the_documented_schemas(workspace: Path) -> None:
    run(workspace / "input_batches", workspace / "output", workspace / "archive", run_ts=RUN_TS)

    assert read_output(workspace, "successful").columns == [
        "membership_id", "first_name", "last_name", "email", "birthday", "above_18", "mobile",
    ]
    assert read_output(workspace, "unsuccessful").columns == [
        "name", "email", "birthday_raw", "mobile_raw", "first_name", "last_name",
        "birthday", "age", "above_18", "rejection_reason", "source_file",
    ]


def test_successful_rows_carry_correct_membership_ids(workspace: Path) -> None:
    run(workspace / "input_batches", workspace / "output", workspace / "archive", run_ts=RUN_TS)
    successful = read_output(workspace, "successful")

    expected = {
        f"Dixon_{hashlib.sha256(b'19860110').hexdigest()[:5]}",
        f"Gonzalez_{hashlib.sha256(b'19730314').hexdigest()[:5]}",
    }
    assert set(successful["membership_id"]) == expected
    assert set(successful["mobile"]) == {"40601711", "66744895"}
    assert set(successful["above_18"]) == {"true"}


def test_rejected_rows_explain_themselves(workspace: Path) -> None:
    run(workspace / "input_batches", workspace / "output", workspace / "archive", run_ts=RUN_TS)
    unsuccessful = read_output(workspace, "unsuccessful")

    # An empty CSV field is read as null, both on the way in and on the way back.
    reasons = dict(zip(unsuccessful["name"], unsuccessful["rejection_reason"]))
    assert reasons["Kristen Horn"] == "invalid_mobile"
    assert reasons["Cathy Werner"] == "under_18"
    assert reasons[None] == "missing_name"
    assert all(reason for reason in unsuccessful["rejection_reason"]), (
        "every rejected row must explain itself"
    )
    assert "membership_id" not in unsuccessful.columns, (
        "the audit file must not look like a source of valid memberships"
    )


def test_processed_batches_are_moved_into_the_archive(workspace: Path) -> None:
    summary = run(
        workspace / "input_batches", workspace / "output", workspace / "archive", run_ts=RUN_TS
    )

    archived = sorted(p.name for p in (workspace / "archive" / STAMP).glob("*.csv"))
    assert archived == ["applications_batch_a.csv", "applications_batch_b.csv"]
    assert len(summary.archived) == 2
    assert list((workspace / "input_batches").glob("*.csv")) == [], (
        "batches must leave the input folder so the next hourly run cannot reprocess them"
    )


def test_no_archive_leaves_the_batches_in_place(workspace: Path) -> None:
    summary = run(
        workspace / "input_batches",
        workspace / "output",
        workspace / "archive",
        archive=False,
        run_ts=RUN_TS,
    )

    assert summary.archived == []
    assert len(list((workspace / "input_batches").glob("*.csv"))) == 2
    assert not (workspace / "archive").exists()


def test_filenames_come_from_the_injected_run_timestamp(workspace: Path) -> None:
    """A scheduler passing its logical date gets reproducible filenames."""
    summary = run(
        workspace / "input_batches", workspace / "output", workspace / "archive", run_ts=RUN_TS
    )

    assert summary.output_paths["successful"].name == f"successful_applications_{STAMP}.csv"
    assert summary.output_paths["unsuccessful"].name == f"unsuccessful_applications_{STAMP}.csv"


def test_rerunning_an_interval_reproduces_identical_output(tmp_path: Path) -> None:
    outputs = []
    for label in ("first", "second"):
        home = tmp_path / label
        batches = home / "input_batches"
        batches.mkdir(parents=True)
        (batches / "applications_batch_a.csv").write_text(BATCH_A, encoding="utf-8")
        summary = run(batches, home / "output", home / "archive", run_ts=RUN_TS)
        outputs.append(summary.output_paths["successful"].read_bytes())

    assert outputs[0] == outputs[1], "same input and same run_ts must yield identical bytes"


def test_empty_input_is_a_logged_no_op(tmp_path: Path) -> None:
    (tmp_path / "input_batches").mkdir()

    summary = run(tmp_path / "input_batches", tmp_path / "output", tmp_path / "archive")

    assert (summary.files, summary.rows_in, summary.successful, summary.unsuccessful) == (0, 0, 0, 0)
    assert summary.output_paths == {}
    assert not (tmp_path / "output").exists(), "a no-op run must not write empty files"


def test_run_summary_is_json_serialisable_for_xcom(workspace: Path) -> None:
    import json

    summary = run(
        workspace / "input_batches", workspace / "output", workspace / "archive", run_ts=RUN_TS
    )
    payload = json.loads(json.dumps(summary.to_dict()))

    assert payload["successful"] == 2
    assert payload["run_ts"] == RUN_TS.isoformat()
    assert payload["output_paths"]["successful"].endswith(f"successful_applications_{STAMP}.csv")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_exits_zero_and_writes_output(workspace: Path) -> None:
    exit_code = main([
        "--input", str(workspace / "input_batches"),
        "--output", str(workspace / "output"),
        "--archive", str(workspace / "archive"),
        "--log-level", "WARNING",
    ])

    assert exit_code == 0
    assert read_output(workspace, "successful").height == 2
    # The CLI stamps with datetime.now(), so the archive folder name is not STAMP here.
    assert len(list((workspace / "archive").glob("*/*.csv"))) == 2


def test_cli_exits_zero_on_an_empty_input_folder(tmp_path: Path) -> None:
    (tmp_path / "input_batches").mkdir()

    exit_code = main([
        "--input", str(tmp_path / "input_batches"),
        "--output", str(tmp_path / "output"),
        "--log-level", "WARNING",
    ])

    assert exit_code == 0, "an idle hour is not a failure"


def test_cli_exits_non_zero_when_the_input_folder_is_missing(tmp_path: Path) -> None:
    exit_code = main([
        "--input", str(tmp_path / "does_not_exist"),
        "--output", str(tmp_path / "output"),
        "--log-level", "ERROR",
    ])

    assert exit_code == 1, "schedulers must be able to alert on a broken run"


def test_cli_no_archive_flag_is_respected(workspace: Path) -> None:
    exit_code = main([
        "--input", str(workspace / "input_batches"),
        "--output", str(workspace / "output"),
        "--archive", str(workspace / "archive"),
        "--no-archive",
        "--log-level", "WARNING",
    ])

    assert exit_code == 0
    assert len(list((workspace / "input_batches").glob("*.csv"))) == 2

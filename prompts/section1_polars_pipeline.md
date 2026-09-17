You are an expert Data Engineer specializing in Python, Polars, and Functional Programming principles.

### Deliverable Format & Location
The deliverable is a **Python package**, not a notebook: create it at
`submission/section1_data_pipeline/membership_pipeline/` with one module per
checkpoint (`config.py`, `ingest.py`, `transform.py`, `validate.py`, `output.py`)
and a `__main__.py` entry point so the pipeline runs as
`python -m membership_pipeline --input ./input_batches --output ./output`.
Every transformation must be a pure function returning a `pl.LazyFrame` or
`pl.Expr`; the only `.collect()` / sink calls live in `output.py`. Scheduling
artefacts (Airflow DAG, crontab) go in `submission/section1_data_pipeline/scheduler/`.
Do not create Jupyter notebooks; a separate walkthrough notebook will be written
by me afterwards, importing from this package. Include type hints, docstrings and
a module-level logger in every file, and keep `requirements.txt` at the section root.

---

### Objective
Implement an automated, production-grade CSV data pipeline using Python and Polars (`LazyFrame`). The pipeline reads hourly batches of application CSV datasets from a designated input folder, cleans and validates candidate applications, formats required fields, generates secure membership IDs for successful applicants, and outputs processed datasets while isolating failed rows for auditability.

---

### Execution Protocol: Human-in-the-Loop & Incremental Checkpoints
To ensure total control, code quality, and pipeline integrity, you MUST implement this pipeline **incrementally, stage-by-stage**:
1. **One Stage at a Time**: Write and deliver code for **only one checkpoint per response**.
2. **Mandatory Stop**: After presenting the code and explanation for a checkpoint, you MUST **STOP immediately**. Do NOT attempt to output code for subsequent stages.
3. **Explicit Green Light Required**: Wait for the user to review your code and give a "green light" (e.g., "approved", "looks good", "proceed") before moving to the next checkpoint.
4. **Iterative Adjustments**: If the user provides feedback or requests modifications at any checkpoint, revise that specific stage until approved.

---

### Pipeline Checkpoints

#### Checkpoint 1: Ingestion & Schema Definition
- Set up module structure, type hints, and logger configuration.
- Implement batch CSV scanning with `pl.scan_csv()` for input files (`./input_batches/*.csv`).
- Enforce strict schema types on ingestion (`mobile` as String, `birthday` as String/Date, `name` as String, `email` as String).
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

#### Checkpoint 2: Data Cleaning & Formatting (Pure Transformations)
- Filter out rows where `name` is null or empty string (marked as unsuccessful).
- Split `name` into `first_name` and `last_name` (handling missing last names gracefully).
- Standardize `birthday` field into `YYYYMMDD` string format.
- Compute age as of **1 January 2022** (`2022-01-01`) and create the boolean field `above_18`.
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

#### Checkpoint 3: Validity Filtering & Membership ID Generation
- Implement pure predicate expressions to determine application success:
  1. `name` field present (non-null and non-empty).
  2. `mobile` number consists of **exactly 8 digits** (`^\d{8}$`).
  3. `above_18` is `True` (applicant > 18 as of 1 Jan 2022).
  4. `email` ends with `@emailprovider.com` or `@emailprovider.net` (case-insensitive).
- Compute `membership_id` for successful rows: `<last_name>_<hash(YYYYMMDD)>` using the first 5 hex characters of the SHA-256 hash of `YYYYMMDD`.
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

#### Checkpoint 4: Output, Archival & Scheduling
- Implement `output.py` as the **only** module that materialises the `LazyFrame`:
  1. Partition the validated frame into `successful` and `unsuccessful` using the predicates from Checkpoint 3 (`pl.LazyFrame.filter` on the combined `is_successful` expression, and its negation).
  2. Successful rows: select `membership_id, first_name, last_name, email, birthday, above_18, mobile` and sink to `./output/successful/successful_applications_<YYYYMMDD_HHMMSS>.csv`.
  3. Unsuccessful rows: keep the original raw columns plus derived fields and a `rejection_reason` column (a `;`-joined list of every failed predicate — not just the first) and sink to `./output/unsuccessful/unsuccessful_applications_<YYYYMMDD_HHMMSS>.csv`.
  4. The run timestamp must be a single value injected once (function parameter, default `datetime.now()`), so all files from one run share the same stamp and a scheduler can pass its logical run time for deterministic re-runs.
- Implement `archive_batches(files, archive_dir, run_ts)` that moves every processed input file to `./archive/<run_ts>/`, so the next hourly run never re-processes the same batch. Handle the empty-input case as a logged no-op with exit code 0, not an error.
- Implement `__main__.py` with `argparse` (`--input`, `--output`, `--archive`, `--no-archive`, `--log-level`) that wires ingest → transform → validate → output → archive, logs a one-line run summary (`files`, `rows_in`, `successful`, `unsuccessful`, `output_paths`) and returns non-zero on any exception so schedulers can alert.
- Add scheduling artefacts under `./scheduler/`:
  - `crontab`: an hourly entry running `python -m membership_pipeline` from the section root, with stdout/stderr appended to `logs/pipeline.log`.
  - `airflow_dag.py`: an `@hourly` DAG with `catchup=False`, `max_active_runs=1`, 2 retries, and three tasks: `check_for_files` (`ShortCircuitOperator`) → `process_applications` (`PythonOperator` calling the package with `logical_date` as `run_ts`) → `publish_summary` (reads the summary via XCom).
- Add `requirements.txt` at the section root (`polars` pinned to a major version; `apache-airflow` listed as an optional extra with a comment).
- Run the pipeline end-to-end on the sample batches in `./input_batches/` and report the row counts per output file and the `rejection_reason` distribution in your response.
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

#### Checkpoint 5: Tests & Documentation
- Add `tests/` with `pytest` unit tests for each pure function/expression from Checkpoints 2–3 (name splitting incl. salutations/suffixes, each birthday format, 29-Feb and boundary-date `above_18` cases, mobile regex, email predicate, `membership_id` against a known SHA-256 vector) and one integration test that runs `__main__` on a temp folder with a two-file fixture and asserts the output row counts and archive move.
- Write `README.md` for the section covering: folder layout, how to install and run, how to schedule (cron and Airflow), output schemas, run results on the sample data, and an explicit **Assumptions** list (date-format disambiguation, whitespace handling in mobile numbers, the email-domain interpretation, salutation/suffix handling, membership-ID uniqueness limits, idempotency/re-run behaviour).
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

---

### Architecture & Functional Programming Guidelines
Throughout all checkpoints, enforce these core FP principles:
- **Lazy Evaluation (`LazyFrame`)**: Maintain declarative transformation graphs before terminal collection to maximize Polars query planning optimizations.
- **Immutability & Pure Functions**: All operations must return new `LazyFrame` nodes without mutating source states or using global side-effects.
- **Declarative Composition**: Use native Polars expressions (`pl.col(...)`) and string/date functions.
- **Monadic Safety**: Handle missing or malformed data gracefully without raising unhandled runtime exceptions.
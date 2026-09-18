# Section 1 — Membership Application Pipeline

An hourly Polars pipeline that ingests batches of membership applications, cleans and
validates them, mints membership IDs for successful applicants, and writes successful and
unsuccessful applications to separate folders for downstream consumers.

Built on `pl.LazyFrame` throughout. Every transformation is a pure function returning a
`pl.LazyFrame` or `pl.Expr`; the query graph stays lazy from ingestion to output, and
`output.py` is the only module that materialises it or touches the filesystem on the way out.

---

## Folder layout

```
section1_data_pipeline/
├── membership_pipeline/
│   ├── config.py        Every business rule and schema, as named constants. No logic.
│   ├── ingest.py        Batch discovery + pl.scan_csv with a strict String schema.
│   ├── transform.py     Pure cleaning: name split, birthday parse, age, mobile normalise.
│   ├── validate.py      Validity predicates, rejection reasons, membership IDs.
│   ├── output.py        The only module that collects, writes and archives.
│   └── __main__.py      CLI entry point; `run()` is the importable form.
├── scheduler/
│   ├── crontab          Hourly cron entry, logging to logs/pipeline.log.
│   └── airflow_dag.py   @hourly DAG: check_for_files → process_applications → publish_summary.
├── tests/               134 pytest tests (unit + end-to-end).
├── input_batches/       Where hourly batches are dropped. Seeded with the sample data.
├── output/
│   ├── successful/      successful_applications_<YYYYMMDD_HHMMSS>.csv
│   └── unsuccessful/    unsuccessful_applications_<YYYYMMDD_HHMMSS>.csv
├── archive/<run_ts>/    Processed batches, moved here so they are never reprocessed.
├── logs/                Cron redirects stdout and stderr here.
└── requirements.txt
```

## Install and run

```bash
cd submission/section1_data_pipeline
pip install -r requirements.txt

python -m membership_pipeline --input ./input_batches --output ./output --archive ./archive
```

All arguments are optional and default to the paths above, so a bare
`python -m membership_pipeline` works from this folder.

| Flag | Default | Purpose |
|---|---|---|
| `--input` | `./input_batches` | Folder the hourly batches are dropped into |
| `--output` | `./output` | Root for the `successful/` and `unsuccessful/` results |
| `--archive` | `./archive` | Root for processed-batch archival |
| `--no-archive` | *(off)* | Leave batches in place — they will be reprocessed next run |
| `--log-level` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |

**Exit codes.** `0` on success, including a run that found no batches — an idle hour is
normal, not a failure. `1` on any unhandled exception, with the traceback logged, so cron
and Airflow can alert on it.

```bash
python -m pytest tests/ -q      # 134 passed
```

## Scheduling

### cron

```bash
crontab scheduler/crontab
```

Edit `PIPELINE_HOME` and `PYTHON` at the top of the file first. The entry runs at the top of
every hour and appends both stdout and stderr to `logs/pipeline.log`, so the run summary and
any traceback land in the same file. A second entry rotates that log monthly.

### Airflow

Copy or symlink `scheduler/airflow_dag.py` into `$AIRFLOW_HOME/dags/`, with this folder on
`PYTHONPATH` (or `pip install -e` it). The DAG calls `run()` directly rather than shelling
out, so cron and Airflow execute the same code and failures surface as real tracebacks.

| Setting | Value | Why |
|---|---|---|
| `schedule` | `@hourly` | Matches the batch drop cadence |
| `catchup` | `False` | Don't replay every hour since the start date on first deploy |
| `max_active_runs` | `1` | Concurrent runs would race over the input folder, and one could archive a batch another is still reading |
| `retries` | `2` (5 min apart) | Covers transient filesystem problems |

Three tasks: `check_for_files` (a `ShortCircuitOperator` that skips the run when the input
folder is empty, keeping the DAG green instead of alerting on an idle hour) →
`process_applications` (passes Airflow's `logical_date` as the run timestamp) →
`publish_summary` (reads the summary from XCom; this is the seam where a real deployment
would post to Slack or notify downstream).

## Output schemas

**`successful_applications_<YYYYMMDD_HHMMSS>.csv`** — for downstream engineers. Cleaned
values only.

| Column | Type | Notes |
|---|---|---|
| `membership_id` | string | `<last_name>_<hash>`, e.g. `Smith_c7677` |
| `first_name` | string | |
| `last_name` | string | Empty for a mononym |
| `email` | string | As submitted |
| `birthday` | string | `YYYYMMDD` |
| `above_18` | boolean | Always `true` here |
| `mobile` | string | 8 digits, whitespace removed |

**`unsuccessful_applications_<YYYYMMDD_HHMMSS>.csv`** — for auditing. Carries the raw
submission *and* what the pipeline derived from it, so a reviewer can see both what the
applicant typed and how it was read.

| Column | Notes |
|---|---|
| `name`, `email` | Exactly as submitted |
| `birthday_raw`, `mobile_raw` | Exactly as submitted |
| `first_name`, `last_name`, `birthday`, `age`, `above_18` | Derived; `null` where the input could not be read |
| `rejection_reason` | **Every** failed rule, `;`-joined |
| `source_file` | Which batch file the row arrived in |

No `membership_id` column: the audit file must not be mistakable for a source of valid
memberships.

Reason codes, in the order they appear: `missing_name`, `unparseable_birthday`, `under_18`,
`invalid_mobile`, `invalid_email`.

> **Reading these files back.** `birthday` and `mobile` are digit *strings*. Default CSV type
> inference — in Polars, pandas and most other readers — will type them as integers and strip
> any leading zero, turning `08123456` into `8123456`. Quoting on write does not prevent this;
> it is inherent to CSV. Read them with an explicit schema:
>
> ```python
> pl.read_csv(path, schema_overrides={"mobile": pl.String, "birthday": pl.String})
> ```
>
> No mobile in the supplied sample data begins with a zero, so nothing is currently lost.

## Run results on the sample data

Both supplied datasets (`applications_dataset_1.csv`, `applications_dataset_2.csv`) placed in
`input_batches/`:

```
files=2  rows_in=4999  successful=695  unsuccessful=4304  archived=2   exit 0
```

Rejection reasons, by combination:

| Rows | Share | `rejection_reason` |
|---:|---:|---|
| 2035 | 47.3% | `invalid_mobile` |
| 855 | 19.9% | `invalid_mobile;invalid_email` |
| 614 | 14.3% | `under_18;invalid_mobile` |
| 291 | 6.8% | `invalid_email` |
| 253 | 5.9% | `under_18;invalid_mobile;invalid_email` |
| 178 | 4.1% | `under_18` |
| 77 | 1.8% | `under_18;invalid_email` |
| 1 | 0.0% | `unparseable_birthday;invalid_mobile` |

By individual rule (a row may fail several):

| Rule | Failures |
|---|---:|
| `invalid_mobile` | 3758 |
| `invalid_email` | 1476 |
| `under_18` | 1122 |
| `unparseable_birthday` | 1 |
| `missing_name` | 0 |

Of the 695 successful applications, **694 membership IDs are unique** — see Assumption 5.

---

## Assumptions

Each of these is a judgement call where the brief was ambiguous or the supplied data
contradicted a literal reading. All are encoded as named constants in `config.py`, marked
`ASSUMPTION`, so they can be changed in one place.

### 1. Source column names

The brief refers to `birthday` and `mobile`; the supplied datasets use `date_of_birth` and
`mobile_no`. Treated as the same fields and renamed once at the ingestion boundary
(`config.COLUMN_ALIASES`).

### 2. Email domain — `.com` / `.net`, not a literal `@emailprovider`

The brief says an email is valid if it ends with `@emailprovider.com` or
`@emailprovider.net`. **No row in either supplied dataset uses that domain** — there are
3,351 distinct domains across the sample, none of them `emailprovider`. Taken literally the
pipeline would produce zero successful applications, and Section 2 (which needs the first 50
members of a processed dataset from Section 1) would have nothing to work with.

`@emailprovider.com` is therefore read as a *placeholder* for the membership provider's
domain, and the rule is applied at the top-level domain: an email is valid if it ends with
`.com` or `.net`, case-insensitively. Configured in `config.ACCEPTED_EMAIL_SUFFIXES`; to
enforce the literal reading instead, change that tuple to
`("@emailprovider.com", "@emailprovider.net")`.

### 3. Date formats — the separator determines the component order

Four formats appear in the sample data, in roughly equal proportions:

| Format | Rows | Example |
|---|---:|---|
| `%Y-%m-%d` | 1266 | `1974-09-10` |
| `%Y/%m/%d` | 1260 | `1986/01/10` |
| `%m/%d/%Y` | 1254 | `02/27/1974` |
| `%d-%m-%Y` | 1219 | `14-03-1973` |

The last two are ambiguous in isolation — `12/09/1992` could be 12 September or 9 December.
The separator resolves it, and the data is unanimous: among slash-dates, **760 rows have a
second component greater than 12** and none have a first component greater than 12; among
dash-dates, **735 rows have a first component greater than 12** and none have a second
component greater than 12. There is not one counter-example in 4,999 rows.

So `/` means month-first and `-` means day-first. Anything matching neither — including
impossible dates such as `1996/02/31` — parses to `null` and is rejected as
`unparseable_birthday` rather than silently guessed. Exactly one sample row is affected.

### 4. Mobile numbers — whitespace is formatting, not data

304 sample rows write the number with an internal space, e.g. `6655 1251`. Whitespace is
stripped before the `^\d{8}$` check, so those applications are judged on their digits. This
admits 1,241 valid mobiles rather than 937. Only whitespace is stripped — `6655-1251` is
still invalid, since punctuation could signal a genuinely different number format. The raw
value is preserved as `mobile_raw` in the audit file.

### 5. Membership IDs are not guaranteed unique

The brief defines the ID as `<last_name>_<first 5 hex of SHA-256(YYYYMMDD)>`. It is a
function of surname and birthday alone, so two different people who share both receive the
same ID. This happens once in the sample data:

```
Kenneth Williamson  10-03-1954  ->  19540310  ->  Williamson_2b72a
Bethany Williamson  1954/03/10  ->  19540310  ->  Williamson_2b72a
```

694 unique IDs for 695 successful applicants. Left as specified rather than silently
disambiguated, since changing the format would break the brief's contract. Truncating to 5
hex characters also means only 1,048,576 distinct hash values, so collisions grow with
volume. **If these IDs are to be primary keys downstream, the format needs revisiting** —
adding a sequence number or widening the hash would fix it.

### 6. Names — salutations and suffixes are stripped

A leading honorific (`Mr`, `Mrs`, `Ms`, `Miss`, `Mx`, `Dr`, `Prof`, `Rev`, `Sir`, `Madam`)
and a trailing post-nominal (`Jr`, `Sr`, `II`–`V`, `MD`, `DDS`, `DVM`, `PhD`, `Esq`, `DO`,
`RN`) are removed before splitting. Matching is case-insensitive and ignores a trailing dot,
so `Mr`, `Mr.` and `MR.` all match. In the sample, 201 names carry one or both; every name
reduces to exactly two tokens once stripped.

The first remaining token is `first_name`; everything after it is `last_name`, so a middle
name stays with the surname (`Mary Ann Smith` → `Mary` / `Ann Smith`) rather than being
discarded. A suffix is only stripped when a name would remain, so an applicant recorded
solely as `MD` keeps it.

A mononym (`Cher`) gets `last_name = ""` — they did supply a name, so they remain eligible,
and their ID is simply `_<hash>`. An empty string is distinct from `null`, which is reserved
for "no name at all": `null`, `""`, whitespace only, or a bare salutation such as `Mr.`.
Those are rejected as `missing_name`.

### 7. "Over 18" means strictly greater than 18

An applicant who is exactly 18 on 1 January 2022 does **not** qualify. Age is computed by
calendar comparison rather than dividing a day count, so it is exact on leap days: someone
born 2004-02-29 is 17 on 2022-01-01, because their birthday has not yet come round.
The reference date is a parameter (`config.REFERENCE_DATE`), not a hard-coded global.

### 8. Re-runs, idempotency and archival

Processed batches are **moved** into `archive/<run_ts>/` after the outputs are safely
written. That is what makes the hourly schedule safe to repeat: a batch cannot be picked up
twice and double-counted. Archiving happens last, so a failure mid-run leaves the input
untouched and the run can simply be repeated.

The run timestamp is resolved **once** per run and threaded through every filename, so all
artefacts of a run share a stamp. It defaults to `datetime.now()`, but a scheduler should
pass its logical run time — Airflow passes `logical_date` — which makes a replayed interval
reproduce byte-identical output under the same filenames rather than accumulating duplicates.

Because a replay targets an archive folder that may already hold those filenames, and
`shutil.move` onto an existing path silently overwrites on POSIX and errors on Windows,
archival steps aside to `applications_dataset_1_1.csv` and logs a warning instead. The audit
trail is never overwritten.

Rows are **never** silently dropped. Every application lands in exactly one output file:
`successful + unsuccessful == rows_in`, asserted in the tests. This is why every validity
predicate is explicitly null-safe — in Polars `null & True` is `null`, and
`LazyFrame.filter` drops null rows, so an unguarded predicate would make a malformed
application vanish from both files rather than appear in the audit.

### 9. Row order

Batch files are processed in sorted filename order and rows keep their source order, so a
re-run over the same input produces byte-identical output. No sorting is applied beyond that.

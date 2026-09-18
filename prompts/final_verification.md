You are an independent assessor reviewing a Data Engineer technical assessment submission before it is handed in. You did not write any of it. Your job is to find what is missing, broken or inconsistent — not to praise what is present. Be adversarial: assume every claim in a README is false until you have verified it by running or reading the thing it describes.

### Ground truth
The requirements are in `instructions/README.md` (three sections) and the submission rules are in the root `README.md` (AI policy, prompt logging, commit hygiene). The candidate's own prompts in `prompts/section1_polars_pipeline.md`, `prompts/section2_database.md` and `prompts/section3_system_design.md` define the deliverable shape they committed to (package layout, CLI flags, DAG settings, DDL constraints, query columns, diagram nodes) and are the second source of truth. Read all of them in full before anything else. Every finding must cite the requirement line it relates to.

### Setup (do this first)
- Run every execution check from a **fresh clone in a temp directory** (`git clone <repo> <tmp>/clean`), never in the working tree: the Section 1 pipeline moves its input files to `archive/<run_ts>/`, and `input_batches/` and `archive/20260918_104159/` are already byte-identical copies, so a run in place re-archives the committed inputs.
- Use a **separate virtual environment** for verification. `nbconvert`, `nbformat`, `ipykernel` and `pillow` are not in the section's `requirements.txt`; install them into the verification venv only.
- Section 2's `docker-compose.yml` hardcodes `container_name: section2_sales_db` and the compose project name comes from the folder name, so a clone collides with any running stack from the working tree. Run `docker compose down -v` in the original folder before bringing the clone up. Postgres skips `/docker-entrypoint-initdb.d/` when the data volume is non-empty, so a stale volume silently invalidates Part C.
- Host port 5432 may be taken locally; `.env` accepts `HOST_PORT=<port>` (README §"How to run").
- Column and file names used by this project: successful output columns are `membership_id, first_name, last_name, email, birthday, above_18, mobile` (the column is `mobile`, not `mobile_no`); the unsuccessful output keeps `name, email, birthday_raw, mobile_raw` plus `first_name, last_name, birthday, age, above_18, rejection_reason, source_file`. Raw input columns are `name, email, date_of_birth, mobile_no`. Rejection reason codes: `missing_name, invalid_mobile, under_18, invalid_email, unparseable_birthday`.

### Rules
- **Verify by execution, not by reading.** If a README says "run X", run X. If it says "706 successful rows", count them. If a query is documented with a result set, execute the query and diff.
- **Do not fix anything.** Report only. Changing the submission during verification would contaminate the prompt logs.
- **Do not skip a check because it is slow.** Docker builds and full pipeline runs are in scope.
- **Report as a checklist** with one line per item: `PASS` / `FAIL` / `WARN` / `N/A`, the evidence (command + relevant output line), and for FAIL/WARN a one-sentence fix. Finish with an overall verdict and the ordered list of blockers.

---

## Part A — Repository & submission hygiene

1. `submission/README.md`: candidate name, contact email, assessment start date/time filled in (no `<placeholders>` remain); AI Usage Declaration = Yes; it references both `prompt-logger/` and `prompts/`.
2. `git log --oneline`: more than one commit per section; no single "add everything" commit; commit messages describe the change. Flag any commit touching more than one section.
3. No archive files anywhere (`find . -name "*.zip" -o -name "*.tar*" -o -name "*.7z"`), and none in git history (`git log --all --name-only | grep -E "\.(zip|tar|gz|7z)$"`).
4. `prompt-logger/` contains at least one session file per section used with AI; `prompts/README.md` maps every prompt file to a session log (no `<session-id>` placeholders, and not wrapped in a code fence); every session ID it references exists on disk. Session files are unedited: check they are valid JSONL (every line parses) and that growth is **append-only**. The pre-commit hook re-copies the whole live session file on every commit, so `git log --follow` legitimately shows `M` entries for a session that spanned several commits; the test is that for each consecutive pair of commits the older blob is a byte-prefix of the newer one (`git show <old>:<f>` vs `git show <new>:<f>` with `cmp -n <old size>`). Any shrink or in-place change is a FAIL. Also list every commit that touches `submission/section*` without a `prompt-logger/` file in the same commit (the AI policy requires them together).
5. `git config --get core.hooksPath` is `.githooks` **or** the README explains manual export was used.
6. No secrets: `git grep -iE "(password|secret|token|api[_-]?key)\s*[=:]" -- ':!*.md' ':!prompt-logger/'` (the session logs quote system prompts and code and drown the grep in false positives; inspect `.env.example` separately). Any hit that is not an obvious placeholder is a FAIL. Confirm the real `.env` is untracked and git-ignored.
7. No committed junk: `.ipynb_checkpoints`, `__pycache__`, `.DS_Store`, virtualenvs, `output/` files larger than 5 MB.
8. Every `README.md` link (relative) resolves to a file that exists.
9. Root-level or `submission/README.md` gives a top-level index to all three sections with a one-line description each.

## Part B — Section 1: Data Pipelines

From a **clean checkout** (`git stash -u` or a fresh clone in a temp dir):

10. `requirements.txt` exists; `pip install -r` succeeds in a fresh venv.
11. The pipeline runs end-to-end with the documented command on the two sample datasets and exits 0. Record wall time.
12. Outputs land in a `successful/` folder and an `unsuccessful/` folder as the brief requires; both are committed ("submit the processed dataset").
13. Open the successful output and assert programmatically, on **every row**: `first_name` and `last_name` both present; `birthday` matches `^\d{8}$` and is a real calendar date; `above_18` is true and equals the README's definition recomputed from `birthday` (Assumption 7: calendar age **strictly greater than 18** as of 2022-01-01, i.e. 19th birthday on or before 2022-01-01); `mobile` matches `^\d{8}$`; email satisfies the rule stated in README Assumption 2 (lower-cased, ends with `.com` or `.net`); `membership_id` equals `<last_name>_<sha256(birthday)[:5]>` recomputed independently (hex, lowercase, hash of the `YYYYMMDD` string). **Separately** count how many successful rows satisfy the brief's literal rule (`@emailprovider.com` / `@emailprovider.net`) and report the number: the README documents that the literal reading yields zero successes, and the assessor's intent is the risk.
14. Open the unsuccessful output: every row has a non-empty `rejection_reason` (`;`-joined); recompute each rule from `name`, `email`, `birthday_raw`, `mobile_raw` (strip whitespace from the mobile first, README Assumption 4) and confirm the recomputed set of failed rules equals the listed set on every row; confirm no row would have passed all rules (i.e. nothing valid was rejected).
15. `successful + unsuccessful == total input rows` (4,999 = 1,999 + 3,000), and no `(first_name, last_name, email)` triple appears in both files (the successful file does not carry the raw `name`; join on the derived names, or on `email` alone).
16. Name splitting: sample 20 rows whose raw `name` had 3+ tokens (`Mr.`, `Dr.`, `MD`, `PhD`, `Jr.` …) and confirm `last_name` is the family name, not a suffix or title.
17. Date parsing: confirm all four raw layouts (`YYYY-MM-DD`, `YYYY/MM/DD`, `MM/DD/YYYY`, `DD-MM-YYYY`) map to correct `YYYYMMDD` on at least 3 samples each, and that the impossible date in the sample (`1996/02/31`) is rejected, not silently coerced.
18. Rows with a missing/empty name are handled as unsuccessful: inject a row with an empty name into a temp copy of the input, rerun, and confirm it lands in `unsuccessful/`.
19. Idempotency / hourly semantics: run the pipeline twice on the same input folder (in the clone); the second run must log `files=0` and exit 0 because the first run moved the inputs to `archive/<run_ts>/`. Then run twice with `--no-archive` on a temp copy: two output files with distinct `YYYYMMDD_HHMMSS` stamps, each with the same row count, nothing appended. Also diff the fresh run's output against the committed `output/*_20260918_104159.csv` (use `--strip-trailing-cr`; `core.autocrlf` may differ) — they must be identical.
20. Scheduling: a cron entry **and/or** an Airflow DAG exists; the DAG file imports without error (`python -c "import ast; ast.parse(open(f).read())"` at minimum; `airflow dags list` if Airflow is installable); the schedule is hourly.
21. The section README is a proper markdown doc covering: how to run, how to schedule, output schema, and an explicit **Assumptions** list that includes at minimum the email-domain interpretation, mobile-whitespace handling, date-format disambiguation, and membership-ID uniqueness. Confirm the README's row counts match what you observed in step 11.
22. If a notebook exists: it is executed (outputs present, `execution_count` set on every code cell, no stale outputs on unexecuted cells), runs top-to-bottom cleanly (`jupyter nbconvert --to notebook --execute --ExecutePreprocessor.kernel_name=<a kernel that exists> section1_pipeline.ipynb --output <tmp>`; the stored kernel name is `.venv`, which will not exist on the verifier's machine), and its cells match the cell table in the README's "Quick demo" section. Its results agree with the script's (it runs an 8-row in-memory demo, not the sample batches: expect `rows_in=8 successful=2 unsuccessful=6`).
23. If tests exist: `pytest` passes. If not: WARN.

## Part C — Section 2: Databases

24. `Dockerfile` exists and is based on the official `postgres` image; DDL is copied into `/docker-entrypoint-initdb.d/`.
25. From clean: `cp .env.example .env` (add `HOST_PORT=<free port>` if 5432 is taken), `docker compose down -v && docker compose up -d --build` brings the DB to healthy (`docker inspect --format '{{.State.Health.Status}}' section2_sales_db`). Record the time to healthy. Run queries with `docker compose exec -T db psql -U ecommerce -d ecommerce < queries/<file>.sql`; under Git Bash `-f /queries/...` gets path-mangled unless `MSYS_NO_PATHCONV=1` is set (README §"Running SQL").
26. `\dt` shows tables covering members, items, transactions and a transaction–item association; every FK has a matching PK; `\d+` shows NOT NULL / CHECK / UNIQUE constraints consistent with the README.
27. `SELECT COUNT(*) FROM members` = 50, and those 50 `membership_id`s are exactly the first 50 rows of the Section 1 successful output (order-preserving compare). Flag if a duplicate `membership_id` was skipped and whether the README says so.
28. Items carry name, manufacturer, cost, weight (kg); transactions carry membership_id, total items price, total items weight; line items link items to transactions — all four attribute sets from the brief are present and typed sensibly (NUMERIC not FLOAT for money).
29. Integrity: for every transaction, `total_items_price` equals `SUM(quantity × unit_cost_at_purchase)` and `total_items_weight` equals `SUM(quantity × unit_weight_at_purchase)` over its line items (query it; zero mismatches). The DDL uses a **row-level** trigger on `transaction_items` that recomputes the header (the Section 2 prompt asked for statement-level with transition tables; `ddl/01_schema.sql:240-247` and the README explain why Postgres forbids that on a multi-event trigger). Accept the row-level form if the behaviour holds: inside `BEGIN … ROLLBACK`, insert a header with deliberately wrong totals (`OVERRIDING SYSTEM VALUE`), add two line items, update a quantity, delete a line — after each step the header must equal the line-item sums. Note and report that a direct `UPDATE transactions SET total_items_price=…` with no line-item change is not reverted (no trigger on `transactions`).
30. Every member has ≥ 1 transaction and every item is referenced at least once (or the README explains why not).
31. Run `queries/top10_members_by_spending.sql` and `queries/top3_items_by_frequency.sql` (or equivalents): both execute, return 10 and 3 rows, are deterministic on re-run, and the result sets match those printed in the README. Recompute the top-10 spend independently with your own query and diff.
32. The "frequently bought" metric is defined explicitly (distinct transactions vs. quantity) in the query header or README.
33. `EXPLAIN (ANALYZE, BUFFERS)` on both queries: the PASS criterion is that the plan **matches what the README claims**, not that an index is used. At 50 members / 150 transactions the README states both queries sequential-scan and that this is correct planner behaviour; it then shows the indexes engaging under a rolled-back inflation to 200k rows. Reproduce that: `BEGIN; INSERT INTO transactions (membership_id, transaction_ts) SELECT … FROM generate_series(1,200000); ANALYZE transactions; EXPLAIN ANALYZE <filter on membership_id / transaction_ts>; ROLLBACK;` and confirm `transactions_membership_id_idx` and `transactions_transaction_ts_idx` appear.
34. ERD: an editable source exists (`erd/erd.mmd`, Mermaid) and is embedded verbatim in the README (diff the two). There is deliberately **no rendered image** — the Section 2 prompt chose Mermaid-only because GitHub renders it natively; record WARN, not FAIL. Every table and FK in the DDL appears in the ERD with correct cardinality; no table appears in the ERD that is not in the DDL.
35. The README explains the schema design (normalisation, snapshotting of unit price, persisted totals), how to run, how to regenerate the seed, and an **Assumptions** section.
36. Seed generation is reproducible: run `python generate_seed.py --self-check`, then the generator twice with `--output-dir <tmp1>` / `<tmp2>` **and `--section1-output` pointed at the committed `successful_applications_20260918_104159.csv`**, and diff the two outputs against each other and against `ddl/02–04` (all identical, i.e. seeded RNG). Without `--section1-output` the generator picks the newest `successful_applications_*.csv` by filename, so any pipeline run made during verification changes the reference date and every seed file — that is expected, not a defect, but say so.
37. Teardown: `docker compose down -v` leaves no containers/volumes behind.

## Part D — Section 3: System Design

38. An architecture diagram exists as an editable source (`.drawio`, `.vsdx` or `.pptx`) **and** a rendered image; the image is legible at 100 % zoom (no overlapping labels, no truncated text). Open the image and look at it.
39. The diagram shows, as distinct elements: (a) the REST API upload path, (b) the Kafka stream path, (c) where the pre-written processing code runs, (d) image storage, (e) metadata storage, (f) the 7-day purge mechanism, (g) the BI resource, (h) the analysts. Missing any one is a FAIL.
40. The Kafka component is described in a way consistent with "managed by the company's engineers" — if a fully cloud-managed Kafka is used, the README must justify it explicitly; otherwise FAIL.
41. The README has an explicit **Assumptions** section, and a component-by-component explanation that covers every element in the diagram (walk the diagram, tick each element off in the text; list any unexplained element).
42. The 7-day purge is addressed for **every** place data can persist (raw images, processed images, metadata store, message queue/topic retention, query-result caches, BI caches, logs, backups/versioning). List which of these the README covers and which it silently omits.
43. Failure handling is addressed (retries/DLQ, scaling, AZ loss) at least briefly.
44. The diagram and README use the same component names (grep 5 names from the diagram in the README).

## Part E — Cross-section consistency

45. Section 2's member seed references the exact Section 1 output file/columns; column names (`membership_id`, `birthday` …) match between Section 1 output, Section 2 DDL and Section 2 README.
46. The prompts in `prompts/` describe the deliverables that actually exist (e.g. if a prompt specifies Polars and the code uses pandas, or a folder name differs, flag it — the assessor will notice).
47. Terminology is consistent across all READMEs (e.g. `mobile` vs `mobile_no` vs `mobile_number`). The raw input column is `mobile_no` and the output column is `mobile`; a README mention of `mobile_no` is correct only when it describes the source column.
48. `submission/README.md` (or the root README) gives a top-level index to all three sections with a one-line description and a link to each section README. This duplicates A9 on purpose: it is a blocker, not a nicety — the root README's submission guidelines ask for a main README that points to the sub-directory docs.

---

### Output format
```
## Verdict: READY / NOT READY
### Blockers (must fix before submitting)
1. …
### Warnings (should fix)
1. …
### Checklist
A1 PASS — evidence…
A2 FAIL — evidence… → fix: …
…
```
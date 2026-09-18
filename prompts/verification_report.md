# Verification report — Data Engineer assessment submission

Run on 2026-09-19 against commit `f58dd63` following the process in [`final_verification.md`](final_verification.md). Every execution check ran in a fresh clone of the repository in a temporary directory with a separate virtual environment; the working tree of the submission was not modified during verification. Section 2 was verified from `docker compose down -v` (the pre-existing local stack was removed first).

## Verdict: NOT READY (3 blockers, all documentation; code, data and database verified clean)

### Blockers (must fix before submitting)
1. **A9 — no section index.** Neither `submission/README.md` nor the root README names the three sections or links to their READMEs. A reviewer landing on the repo has to guess from folder names.
2. **A4 — `prompts/README.md` is unfilled and mis-rendered.** All three rows still carry the literal `<session-id>` placeholder, and the whole body is wrapped in a ```` ```markdown ```` fence so GitHub renders it as a code block. The mapping is knowable from the session logs: Section 1 → `10853dc6`, Section 2 → `987361e7`, Section 3 → `0579bb73` + `79f1f383`, final verification → `507aa281`.
3. **B22 — notebook committed without executed outputs.** `section1_pipeline.ipynb` executes cleanly top-to-bottom under nbconvert (exit 0, 0 error outputs, prints `rows_in=8 successful=2 unsuccessful=6`), but the committed file has `execution_count=None` and no outputs on the five demo cells, one stale output on an exploration cell, and two leading cells that read `instructions/` rather than the pipeline. The README's "Cell 1…5" table therefore points at the wrong cells.

### Warnings (should fix, or decide consciously)
1. **B13 — email rule is a documented deviation from the brief's literal text.** `config.py` accepts any `.com`/`.net` domain. Recomputed: **0 of 695** successful rows end in `@emailprovider.com|.net`; the literal rule would produce an empty successful file. README Assumption 2 states this. Left as-is; the assessor's intent is the risk.
2. **C29/E46 — trigger is `FOR EACH ROW`, not the statement-level trigger the Section 2 prompt specified.** Behaviour verified correct (see C29). The deviation is explained in `ddl/01_schema.sql:240-247` and README §"Keeping the totals honest" with the Postgres error that motivates it.
3. **A4 — commit `ca9e374` (ERD) carries no prompt-logger file.** The other 15 section commits all do. Not fixable without rewriting history; the session content is present in neighbouring commits.
4. **D42 — Amazon ECR is in the diagram but absent from the §5 purge table.** Defensible (container images hold no customer data) but it is the one store the table does not name.
5. **B21/C35 — Section 2 README says the membership-ID collision "sits at roughly row 450".** It is at data rows 273 and 436 (`grep -n Williamson_2b72a`). The substantive claim (first 50 rows collision-free) is correct.
6. **C36 — the seed generator anchors to the *newest* `successful_applications_*.csv` by filename.** After any later pipeline run the regenerated seed changes (observed: a run on 2026-09-19 moved the anchor and all three SQL files differed). With `--section1-output` pointed at the committed file the output is byte-identical to `ddl/`. The README's "regenerate → `git status` shows nothing" holds only while a single output file exists.
7. **C25 — `.env.example` leaves `HOST_PORT` commented and defaults to 5432.** On a machine with a local Postgres the stack fails to bind. README §"How to run" anticipates this; the example file could carry the override.
8. **A7 — untracked `bash.exe.stackdump` at the repository root** (Git Bash crash artefact). Delete; do not commit.
9. **B10 — `polars>=1.44,<2` is a major-version range, not an exact pin.** Satisfies the prompt's "pinned to a major version" wording; `uv.lock` pins 1.44.2.
10. **B20 — Airflow is not installed; the DAG was validated by `ast.parse` and grep only.** It imports `airflow.operators.python` (Airflow 2.x path), which the file comments on.
11. **B12 — `output/` and `archive/` are committed and not git-ignored,** and `archive/20260918_104159/` is a byte-identical copy of `input_batches/`. Intentional (the brief asks for the processed dataset), but a second run in the working tree would double the archive. README Assumption 8 covers re-run semantics.

### Checklist

#### Part A — Repository & submission hygiene
- A1 PASS — `cat submission/README.md`: name, email, `Thu, 17 Sep 2026 10:21:11 PM`, AI declaration `Yes`; `grep -c "<"` → 0. Does not mention `prompt-logger/` or `prompts/` beyond the policy link (see A9).
- A2 PASS — 27 commits, cleanly phased (setup → §1 → §2 → §3 → wrap-up); loop over `git show --name-only` per commit: **0** commits touch more than one section folder. WARN: `ca9e374` is the only section commit without a `prompt-logger/` file.
- A3 PASS — `find … -name "*.zip" -o -name "*.tar*" -o -name "*.7z"` → none; `git log --all --name-only | grep -E "\.(zip|tar|gz|7z)$"` → none.
- A4 FAIL — (a) all 7 session files parse: 1,625 JSONL lines, 0 bad. (b) Append-only: for all 16 consecutive commit pairs of a session file, the older blob is a byte-prefix of the newer (`cmp -n`) → OK. (c) `grep -c "<session-id>" prompts/README.md` → 3; line 1 is ```` ```markdown ````. → fix: fill the table, drop the fence.
- A5 PASS — `git config --get core.hooksPath` → `.githooks`.
- A6 PASS — `git grep -iE "(password|secret|token|api[_-]?key)\s*[=:]" -- ':!*.md' ':!prompt-logger/'` → only `.env.example:11:POSTGRES_PASSWORD=ecommerce_local_dev` (placeholder). Real `.env` is untracked and ignored (`.gitignore:157`).
- A7 PASS — `git ls-files | grep -E "__pycache__|ipynb_checkpoints|DS_Store|\.venv/"` → none; largest tracked files are session logs (6.3 MB max) and `architecture.png` (824 KB); no output file over 5 MB. WARN: untracked `bash.exe.stackdump` in the working tree.
- A8 PASS — link checker over all 8 READMEs: 14 relative links, 14 resolve, 0 broken.
- A9 FAIL — `grep -iE "section ?[123]" submission/README.md README.md` → no match. → fix: add a three-row index to `submission/README.md`.

#### Part B — Section 1: Data Pipelines (fresh clone, fresh venv)
- B10 PASS — `pip install -r requirements.txt` → exit 0 (polars 1.44.2, pytest 9.1.1).
- B11 PASS — `python -m membership_pipeline --input ./input_batches --output ./output --archive ./archive` → exit 0; `Run summary | files=2 rows_in=4999 successful=695 unsuccessful=4304 archived=2`. Wall time on a temp copy: 461 ms.
- B12 PASS — new files in `output/successful/` and `output/unsuccessful/`; both committed originals listed by `git ls-files output/`. New run output is identical to the committed files (`diff --strip-trailing-cr` → no differences; the only difference is CRLF from `core.autocrlf=true` on this machine).
- B13 PASS — script over all 695 successful rows: first/last non-empty 0 fails; `birthday` `^\d{8}$` and real date 0 fails; `above_18` all `true` and recomputed (calendar age strictly > 18 at 2022-01-01) 0 fails; `mobile` `^\d{8}$` 0 fails; email per README rule 0 fails; `membership_id == last_name + "_" + sha256(birthday)[:5]` 0 fails. Literal `@emailprovider` rule: 0 of 695 (WARN 1).
- B14 PASS — all 4,304 unsuccessful rows: empty reason 0; at least one listed reason recomputed true 4,304/4,304; reason set exactly equals recomputed set 4,304/4,304; rows that would have passed every rule 0.
- B15 PASS — 695 + 4304 = 4999 = 1999 + 3000 input rows; `(first_name,last_name,email)` overlap between files 0; raw email overlap 0.
- B16 PASS — 20 sampled 3+-token names: `Mr. Larry Grimes MD → Larry | Grimes`, `Gregory Hill III → Gregory | Hill`, `Michael Harris Jr. → Michael | Harris`, `Rhonda Moss DDS → Rhonda | Moss`, `Mrs. Amber Esparza → Amber | Esparza` … all 20 keep the family name.
- B17 PASS — 3 samples per layout: `1986/01/10→19860110`, `1974-09-10→19740910`, `02/27/1974→19740227`, `25-04-1975→19750425` (and 2 more each). `1996/02/31` → unsuccessful with `unparseable_birthday;invalid_mobile`, empty `birthday`; not present in the successful file.
- B18 PASS — injected rows `,injected@…` and `   ,ws@…` into a temp copy → both in `unsuccessful/` with `rejection_reason=missing_name`, 0 in `successful/`; exit 0.
- B19 PASS — second run on the same folder after archiving: `files=0 rows_in=0 … archived=0`, exit 0, no new output. Two `--no-archive` runs: two files with distinct stamps (`…004534`, `…004535`), each 291 rows; nothing appended.
- B20 PASS — `ast.parse(scheduler/airflow_dag.py)` OK; `schedule="@hourly"`, `catchup=False`, `max_active_runs=1`, `"retries": 2`, tasks `check_for_files` (ShortCircuitOperator) → `process_applications` → `publish_summary` (PythonOperator). `scheduler/crontab` line 18 starts `0 * * * *`. Airflow itself N/A (not installed).
- B21 PASS — headings: Folder layout, Install and run, Quick demo, Scheduling (cron, Airflow), Output schemas, Run results, Assumptions 1–9. README line 171 `rows_in=4999 successful=695 unsuccessful=4304` = B11. Assumptions cover email domain (2), date disambiguation (3), mobile whitespace (4), ID uniqueness (5), plus salutations (6), > 18 (7), re-runs (8).
- B22 FAIL — `jupyter nbconvert --execute` → exit 0, 0 error outputs, cell 6 prints `rows_in=8 successful=2 unsuccessful=6`. Committed file: 7 cells, execution counts `9, None×6`, outputs on cell 1 only (stale). → fix: execute in place, drop cells 0–1.
- B23 PASS — `python -m pytest tests/ -q` → `134 passed in 1.16s`.

#### Part C — Section 2: Databases (from `docker compose down -v`)
- C24 PASS — `FROM postgres:16`; `COPY ddl/ /docker-entrypoint-initdb.d/`.
- C25 PASS — `cp .env.example .env` + `HOST_PORT=15432` (5432 occupied locally, WARN 7); `docker compose up -d --build` → `healthy` in 10 s.
- C26 PASS — `\dt` → items, members, transaction_items, transactions. `pg_constraint`: PKs on all four; FKs `transactions→members RESTRICT`, `transaction_items→transactions CASCADE`, `transaction_items→items RESTRICT`; CHECKs cost ≥ 0, weight > 0, quantity > 0, totals ≥ 0, unit cost ≥ 0, unit weight > 0, mobile `^[0-9]{8}$`, `above_18 = (birthday <= 2003-01-01)`; `UNIQUE (item_name, manufacturer_name)`. All match the README walkthrough.
- C27 PASS — `COUNT(*) FROM members` = 50; `SELECT membership_id … ORDER BY ctid` diffed against the first 50 data rows of the committed successful CSV → identical. No duplicate in the first 50 (only duplicate in the file is `Williamson_2b72a` at rows 273/436); README says so (row number off, WARN 5).
- C28 PASS — `cost numeric(10,2)`, `weight_kg numeric(8,3)`, `unit_cost_at_purchase numeric(10,2)`, `unit_weight_at_purchase numeric(8,3)`, `total_items_price numeric(12,2)`, `total_items_weight numeric(10,3)`; no float/money columns.
- C29 PASS — mismatch query (header totals vs `SUM(quantity × unit_*)`) → 0 rows. Rolled-back trigger test: header inserted with totals 999999 → after two line items totals `25.50 / 2.250`; after `UPDATE quantity=3` → `35.50 / 2.750`; after deleting one line → `30.00 / 1.500`. Bogus header totals are overwritten on first line-item write. Note: a direct `UPDATE transactions SET total_items_price=1` with no line-item change is **not** reverted (no trigger on `transactions`); README states totals are owned by the line-item trigger. Trigger is row-level (WARN 2).
- C30 PASS — members with 0 transactions: 0; items never referenced: 0.
- C31 PASS — both query files run via `psql < file`; 10 and 3 rows; re-run byte-identical. Independent recompute from line items (`SUM(quantity × unit_cost_at_purchase)`) → identical top 10. All 13 result rows equal the README tables cell-for-cell (Murphy_0851c 6 5327.40 … Thompson_52cd0 5 2054.60; items 1/7/10 with 63/119, 58/111, 47/93).
- C32 PASS — `top3_items_by_frequency.sql` header: "Metric: times_bought = the number of distinct transactions containing the item"; README Assumption 3 repeats it.
- C33 PASS — `EXPLAIN (ANALYZE, BUFFERS)`: both queries use `Seq Scan` + hash join + top-N heapsort, exactly as README §"Query plans" claims ("neither query uses an index, and that is the planner being right"). Rolled-back inflation to 200k transactions: `Index Scan using transactions_membership_id_idx` and `Index Only Scan using transactions_transaction_ts_idx` engage, as the README shows.
- C34 WARN — `erd/erd.mmd` (Mermaid, 4 entities, 3 relationships, cardinalities) is byte-identical to the block inline in the README. No rendered image; the Section 2 prompt chose Mermaid-only deliberately because GitHub renders it. Every DDL table and FK appears; no extra entities.
- C35 PASS — headings: Folder layout, How to run, ERD, Schema walkthrough (4 tables + delete semantics), Indexes, Keeping the totals honest, The seed, The analyst queries, Query plans, Verification, Assumptions 1–8, How this scales.
- C36 PASS — `generate_seed.py --self-check` → OK; two runs with `--section1-output <committed csv>` → identical to each other and to committed `ddl/02–04`. See WARN 6 for the newest-file behaviour.
- C37 PASS — `docker compose down -v` → no `section2*` container or volume remains.

#### Part D — Section 3: System Design
- D38 PASS — `architecture.png` 2995 × 1730 px RGB, 823 KB; `architecture.drawio` is plain XML (`<mxCell` ×80, no base64). Inspected the image: all node text legible, no truncated or overlapping labels; minor cosmetic: `S3 ObjectCreated` and `outputs` labels sit slightly away from their edges.
- D39 PASS — parsed 32 labelled vertices: REST path (Web app → API Gateway + WAF → Lambda presign → presigned PUT to S3 raw), Kafka path (Kafka web app → Kafka on EKS/Strimzi → Kafka Connect S3 Sink → S3 metadata), processing (SQS + DLQ → ECS on Fargate, ECR), image storage (S3 raw, S3 processed), metadata storage (S3 metadata, DynamoDB image_index), purge (lane title, sticky note, Compliance sweeper with red dashed edges), BI (Glue → Athena → QuickSight), Analysts.
- D40 PASS — README §1, Assumption 2 and §4.2: "Self-managed Apache Kafka on EKS (Strimzi operator)… operated by the engineers"; "Alternative considered: Amazon MSK… hands cluster management to AWS, which reads against the brief."
- D41 PASS — every one of 24 diagram component names greps in the README (0 missing); §2 Assumptions has 9 items; §4 covers each node.
- D42 WARN — §5 table covers S3 raw/processed/metadata (lifecycle 7 d), versioning off, DynamoDB TTL + PITR off + no backups, Kafka `retention.ms`, Connect output, SQS 4 d, Athena results 1 d, QuickSight SPICE off, CloudWatch Logs 7 d, ECS ephemeral, retained aggregates; CloudTrail/access logs 30 d as audit. Silently omitted: **ECR** (WARN 4).
- D43 PASS — §6 table: crash → SQS ×3 → DLQ; Kafka down; burst → autoscale on queue depth; AZ outage (multi-AZ, Kafka 3-AZ `min.insync.replicas=2`); lifecycle mis-config → sweeper; duplicate delivery → idempotent.
- D44 PASS — 24 names checked (API Gateway, Strimzi, Kafka Connect, image_index, metrics/daily, SQS, ECR, Fargate, Glue, Athena, QuickSight, EventBridge, objects_older_than_7d, CloudTrail, Terraform, SPICE …) all present in both.

#### Part E — Cross-section consistency
- E45 PASS — `generate_seed.py` globs `../section1_data_pipeline/output/successful/successful_applications_*.csv`; `02_seed_members.sql` INSERT columns `(membership_id, first_name, last_name, email, birthday, above_18, mobile)` = CSV header.
- E46 PASS with WARN — Section 1 prompt: package layout, flags, DAG settings, tests all present; notebook is the "separate walkthrough" the prompt allows. Section 2 prompt: statement-level trigger vs row-level (WARN 2); every other folder/file name matches. Section 3 prompt: all 20 node names and 6 lane titles, footer and legend present in the drawio.
- E47 PASS — `mobile` used throughout; the single `mobile_no` mention (Section 1 README line 210) correctly names the **source** CSV column (`name,email,date_of_birth,mobile_no`) that is renamed at ingestion.

### Post-fix status

Five fix commits were made after the report above, one per finding, and the failed checks were re-run against the working tree:

| Finding | Commit | Re-check |
|---|---|---|
| A9 / E48 section index | `514fdd4` | `submission/README.md` now has a 3-row Sections table; link checker → 0 broken. **PASS** |
| A4 `prompts/README.md` placeholders + fence | `b2e32ae` | `<session-id>` count 0; file no longer starts with a fence; every linked session file exists. **PASS** |
| B22 notebook not executed | `0b53677` | Cells 0–1 removed; 5 cells with `execution_count` 1–5 and outputs; `nbconvert --execute` on the committed file → exit 0, 0 error outputs, `rows_in=8 successful=2 unsuccessful=6`; cells now match the README's Cell 1–5 table. **PASS** |
| C27 collision row numbers | `fa07b32` | README says "data rows 273 and 436". **PASS** |
| D42 ECR missing from purge table | `9494667` | §5 table has an `Amazon ECR` row. **PASS** |

Re-run of A2 over the five new commits: none touches more than one section. Two of them (`b2e32ae`, `fa07b32`) carry no `prompt-logger/` file, for the same reason as `ca9e374`: the hook copies the live session file, and it had not changed between back-to-back commits made in one step. The session content is in the neighbouring commits; history was not rewritten.

Not fixed, by design (decisions for the candidate, all already documented in the READMEs): the `.com`/`.net` email interpretation (Warning 1), the row-level trigger (Warning 2), the newest-file seed anchor (Warning 6), and the tracked `output/`/`archive/` sample run (Warning 11). `bash.exe.stackdump` (Warning 8) was already gone from the working tree by the time fixes started, and `.env.example` (Warning 7) already carries `HOST_PORT` as a commented line, so neither needed a change.

**Verdict after fixes: READY**, subject to the candidate accepting the documented deviations above.

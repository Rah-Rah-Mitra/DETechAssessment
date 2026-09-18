You are an expert Data Engineer specialising in relational database design, PostgreSQL and Docker.

### Context
Section 1 of this assessment is **already implemented and must not be modified**. It lives at `submission/section1_data_pipeline/` and produces `output/successful/successful_applications_<ts>.csv` with columns:

`membership_id, first_name, last_name, email, birthday (YYYYMMDD string), above_18, mobile_no, source_file`

Section 2 consumes that file. Treat it as an upstream contract: read it, never regenerate it.

### Objective
Design and stand up a containerised **PostgreSQL** database for the e-commerce company's sales transactions, seeded with the **first 50 members** of the Section 1 successful output, and deliver the analytical SQL the company's analysts need. Everything must come up with a single `docker compose up` — no Python required at runtime.

### Deliverable Format & Location
All work goes under `submission/section2_database/`:

```
submission/section2_database/
├── README.md                     # design rationale, ERD, how to run, query results, assumptions
├── Dockerfile                    # FROM postgres:16, copies ddl/ into /docker-entrypoint-initdb.d/
├── docker-compose.yml            # one service, healthcheck, named volume, env vars for creds
├── .env.example                  # POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
├── ddl/
│   ├── 01_schema.sql             # tables, constraints, indexes, comments
│   ├── 02_seed_members.sql       # generated: first 50 members from Section 1
│   ├── 03_seed_items.sql         # generated: item catalogue
│   └── 04_seed_transactions.sql  # generated: transactions + line items
├── queries/
│   ├── top10_members_by_spending.sql
│   └── top3_items_by_frequency.sql
├── erd/
│   ├── erd.dbml                  # editable source (dbdiagram.io syntax)
│   ├── erd.mmd                   # Mermaid erDiagram, embedded in README
│   └── erd.png                   # rendered image
├── generate_seed.py              # deterministic generator that writes ddl/02–04 from Section 1 output
└── requirements.txt              # pandas or polars for generate_seed.py only
```

Do not create Jupyter notebooks. Do not build a Python DB-loader that must run against a live container: the seed is committed as SQL so the assessor can review it and the database stands up from Docker alone. `generate_seed.py` exists only to make the seed reproducible and to prove the Section 1 → Section 2 linkage.

---

### Execution Protocol: Human-in-the-Loop & Incremental Checkpoints
1. **One Stage at a Time**: Deliver code for **only one checkpoint per response**.
2. **Mandatory Stop**: After presenting a checkpoint, **STOP**. Do not start the next stage.
3. **Explicit Green Light Required**: Wait for "approved", "looks good" or "proceed" before continuing.
4. **Iterative Adjustments**: Revise the current checkpoint until approved.
5. **Declare assumptions inline**: whenever you make a modelling choice the brief leaves open, state it in the response *and* record it in the README's Assumptions section when you reach Checkpoint 5.

---

### Pipeline Checkpoints

#### Checkpoint 1: Logical Design & ERD
- Propose a **3NF** schema covering the brief's entities:
  - `members` — from Section 1 (`membership_id` PK, `first_name`, `last_name`, `email`, `birthday` as `DATE`, `above_18`, `mobile_no`).
  - `items` — catalogue (`item_id` PK, `item_name`, `manufacturer_name`, `cost NUMERIC(10,2)`, `weight_kg NUMERIC(8,3)`).
  - `transactions` — purchase header (`transaction_id` PK, `membership_id` FK, `transaction_ts TIMESTAMPTZ`, `total_items_price`, `total_items_weight`).
  - `transaction_items` — M:N junction (`transaction_id` FK, `item_id` FK, `quantity`, `unit_cost_at_purchase`, `unit_weight_at_purchase`; composite PK).
- Justify each decision in prose: why the totals are persisted on the header even though they are derivable (the brief lists them as transaction attributes; they are a snapshot for reporting), why unit cost/weight are snapshotted on the line (catalogue prices change; history must not), and where `manufacturer` would be split into its own table if the business needed manufacturer attributes.
- Note the known upstream caveat: Section 1's `membership_id` is only unique per `(last_name, birthday)` and the sample contains one collision (`Williamson_2b72a`). The `members` PK must still be enforced; state how the seed generator handles a duplicate if one falls within the first 50 rows (skip with a logged warning).
- Produce `erd/erd.dbml` and `erd/erd.mmd` (Mermaid `erDiagram`) with cardinalities. The PNG is rendered in Checkpoint 5.
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

#### Checkpoint 2: Physical DDL & Container
- Write `ddl/01_schema.sql`: `CREATE TABLE`s in dependency order, `NOT NULL`s, `CHECK`s (`cost >= 0`, `weight_kg > 0`, `quantity > 0`, `total_items_price >= 0`), `UNIQUE (item_name, manufacturer_name)`, `ON DELETE RESTRICT` on FKs, and `COMMENT ON TABLE/COLUMN` for every object.
- Indexes: B-tree on `transactions(membership_id)`, `transactions(transaction_ts)`, `transaction_items(item_id)`. Explain in comments which query each index serves.
- Add a trigger (or deferred constraint trigger) that keeps `transactions.total_items_price` / `total_items_weight` equal to `SUM(quantity × unit_cost_at_purchase)` / `SUM(quantity × unit_weight_at_purchase)` over its line items, so the denormalised totals cannot drift. If you choose to enforce this only in the seed generator instead, say why.
- Write `Dockerfile` (`FROM postgres:16`, `COPY ddl/ /docker-entrypoint-initdb.d/`) and `docker-compose.yml` (service `db`, ports `5432:5432`, `env_file: .env`, `pg_isready` healthcheck, named volume). Provide `.env.example`.
- Verify: `docker compose up -d --build`, then `psql -c "\dt"` shows the four tables. Paste the command output.
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

#### Checkpoint 3: Seed Generation
- Write `generate_seed.py` that:
  1. Locates the newest `successful_applications_*.csv` in `../section1_data_pipeline/output/successful/` (path overridable via `--section1-output`).
  2. Takes the **first 50 rows in file order** (document that this is the "first 50 members" interpretation), converts `birthday` to ISO `DATE`, de-duplicates on `membership_id` with a warning, and writes `ddl/02_seed_members.sql` as a single multi-row `INSERT`.
  3. Writes `ddl/03_seed_items.sql` with a catalogue of ~20 items across ~5 manufacturers, realistic costs and weights.
  4. Writes `ddl/04_seed_transactions.sql`: ~150 transactions over the last 90 days, using a **fixed random seed** so output is reproducible, every member has ≥1 transaction, baskets have 1–5 distinct items with quantities 1–3, and header totals are computed from the line items in the generator (so the trigger from Checkpoint 2 passes). Items should be drawn with a skewed distribution so the "top 3" query has a clear answer.
  5. Escapes string literals correctly (`'` → `''`) and wraps each file in `BEGIN; … COMMIT;`.
- Commit the generated SQL files. Re-run `docker compose down -v && docker compose up -d --build` and paste `SELECT COUNT(*)` for each table.
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

#### Checkpoint 4: Analytical Queries
- `queries/top10_members_by_spending.sql`: join `members` → `transactions`, `SUM(total_items_price)`, `ORDER BY … DESC, membership_id`, `LIMIT 10`. Return `membership_id, first_name, last_name, transaction_count, total_spent`.
- `queries/top3_items_by_frequency.sql`: the brief says "frequently bought", which is ambiguous. Implement **number of distinct transactions containing the item** as the primary metric, and include `total_quantity` as a secondary column and tiebreaker; add a commented alternative that ranks by quantity. Return `item_id, item_name, manufacturer_name, times_bought, total_quantity`, `LIMIT 3`.
- Both queries must be deterministic (explicit tiebreakers) and use ANSI joins and CTEs where they aid readability. Add a header comment explaining the business question and grain.
- Run both against the seeded container and paste the result sets. Run `EXPLAIN (ANALYZE, BUFFERS)` on each and confirm the indexes from Checkpoint 2 are used; paste the plan summary.
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**

#### Checkpoint 5: Documentation & Rendering
- Render `erd/erd.png` from the Mermaid or DBML source (`mmdc`, dbdiagram export, or equivalent) and embed it in the README together with the Mermaid block so it renders on GitHub without the image.
- Write `README.md` covering: purpose and link to Section 1; folder layout; how to run (`cp .env.example .env && docker compose up -d --build`); connection details; schema walkthrough table by table with the design rationale from Checkpoint 1; index and trigger rationale; how the seed was generated and how to regenerate it; the two analyst queries with their result sets; an **Assumptions** section (first-50 interpretation, "frequently bought" metric, persisted totals, snapshotted unit prices, synthetic transaction data, membership-ID collision handling); and a short "How this scales" note (partitioning `transactions` by month, read replicas for analysts, a `manufacturers` table if attributes grow).
- Final verification: from a clean state, `docker compose down -v && docker compose up -d --build`, run both queries, confirm they match the README.
- **[STOP HERE AND WAIT FOR USER REVIEW & GREEN LIGHT]**
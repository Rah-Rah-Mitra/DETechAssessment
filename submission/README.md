# Data Engineer Tech Challenge Submission
- **Candidate Name:** `Rahul Mitra` 
- **Contact Email:** `mitrarahul2002@gmail.com`
- **Assessment Start Date:** `Thu, 17 Sep 2026 10:21:11 PM`
- **AI Usage Declaration:** `Yes` (If yes, you must comply with the [AI Usage Policy](../README.md#ai-usage-policy).)
- **Other Declarations:** All AI-assisted work was driven by the authored prompts in [`prompts/`](../prompts/README.md); the raw session captures are in [`prompt-logger/claude-code/`](../prompt-logger). A self-audit against [`prompts/final_verification.md`](../prompts/final_verification.md) is recorded in [`prompts/verification_report.md`](../prompts/verification_report.md).

## Sections

| Section | Folder | What it contains |
|---|---|---|
| 1. Data Pipelines | [`section1_data_pipeline/`](section1_data_pipeline/README.md) | Polars `LazyFrame` package that ingests hourly CSV batches, validates applications, mints membership IDs and writes `successful/` / `unsuccessful/` outputs; cron and Airflow schedulers, 134 pytest tests, walkthrough notebook, and the processed sample dataset. |
| 2. Databases | [`section2_database/`](section2_database/README.md) | Dockerised PostgreSQL 16 with a 3NF sales-transaction schema, a trigger that keeps header totals honest, a reproducible seed built from the first 50 Section 1 members, a Mermaid ERD and the two analyst queries with their results. |
| 3. System Design | [`section3_system_design/`](section3_system_design/README.md) | AWS architecture for an image-processing platform with REST and engineer-managed Kafka ingestion, containerised processing, 7-day purge controls on every store and a BI layer; draw.io source, rendered PNG and a component-by-component explanation with assumptions. |
You are an expert Cloud Data Architect. You have a draw.io MCP server available; use it to build the diagram directly rather than emitting XML by hand.

### Context
Sections 1 and 2 of this assessment are complete and must not be touched. The written design for Section 3 already exists at `submission/section3_system_design/README.md` — **read it first**. Your job is to produce the architecture diagram that matches that document exactly, and then reconcile the two so nothing in the diagram is unexplained and nothing in the README is missing from the diagram.

### Objective
Create `submission/section3_system_design/architecture.drawio` (and export `architecture.png`) depicting the end-to-end flow of an AWS image-processing platform with two ingestion paths (REST API and an engineer-managed Kafka stream), containerised processing of pre-written code, 7-day retention with purge controls on every store, and a BI layer for analysts.

### Deliverable Format & Location
```
submission/section3_system_design/
├── README.md               # exists — source of truth for components, names and assumptions
├── architecture.drawio     # you create this via the draw.io MCP
└── architecture.png        # exported from the diagram, ≥ 2000 px wide, white background
```
Overwrite the placeholder `architecture.drawio` / `architecture.png` if they exist. Do not create additional files.

---

### Execution Protocol: Human-in-the-Loop & Incremental Checkpoints
1. **One Stage at a Time** — deliver only one checkpoint per response.
2. **Mandatory Stop** — after each checkpoint, STOP and wait.
3. **Explicit Green Light** — proceed only on "approved" / "looks good" / "proceed".
4. **Iterative Adjustments** — revise the current checkpoint until approved.
5. **Show your work** — after every checkpoint that changes the diagram, export a PNG and attach or describe it so I can review the visual, not just the tool calls.

---

### Diagram Specification (applies to all checkpoints)

**Canvas & layout**
- Landscape, single page, roughly 1300 × 750 px logical size. Left-to-right data flow. No crossing arrows where avoidable; use orthogonal edge routing with waypoints.
- Six swimlane containers, titled exactly:
  1. `Upstream applications (outside the data platform)` — far left, full height of the top row
  2. `Ingestion`
  3. `Storage — every store has a 7-day purge control`
  4. `Analytics (BI)` — far right, top row
  5. `Processing (pre-written image code, containerised)` — bottom row, under Ingestion + Storage
  6. `Compliance & operations` — bottom row, under Analytics
- A dashed footer box spanning the width: `Cross-cutting: private subnets + VPC endpoints for S3/DynamoDB · SSE-KMS at rest, TLS/mTLS in transit · one least-privilege IAM role per component (only the sweeper may delete) · CloudWatch metrics & alarms`.

**Icons & styling**
- Use the built-in **AWS 2025 / AWS4 shape library** (`mxgraph.aws4.*`) for every AWS service; use the Apache Kafka logo shape or a plain rounded rectangle labelled "Apache Kafka" for Kafka; plain rounded rectangles (purple `#E1D5E7` / `#9673A6`) for the two upstream apps and the analysts.
- Colour families: ingestion/compute = AWS blue, storage = AWS green for S3 and red-orange for DynamoDB, messaging (Kafka, SQS) = AWS orange, analytics = AWS purple, compliance = red `#F8CECC` / `#B85450`.
- Every node label is `Service name` on line 1 and a 1–3 line role description beneath in smaller text. Use `<br>` line breaks with `html=1`.
- Data-store shapes must show the S3 prefix pattern, e.g. `S3 raw/dt=YYYY-MM-DD/`.

**Nodes (must match README §4 names)**
- Upstream: `Web app (users upload images via REST API)`, `Kafka web app (publishes image events)`
- Ingestion: `Amazon API Gateway + AWS WAF`; `Lambda: presign (validate, mint image_id, return presigned PUT URL)`; `Apache Kafka on EKS (Strimzi) — owned & operated by the company's engineers — topic retention = 7 d`; `Kafka Connect S3 Sink connector (engineer-operated)`
- Storage: `S3 raw/dt=YYYY-MM-DD/ (original uploads)`; `S3 processed/dt=…/ (outputs of processing code)`; `S3 metadata/dt=…/ (Parquet, 1 row per image)`; `DynamoDB image_index (status, keys, TTL expires_at)`; `S3 metrics/daily/ (aggregates only, no image_id — retained > 7 d, see assumption 6)`
- Processing: `SQS image-work queue + dead-letter queue (retry ×3, 4-day retention)`; `Amazon ECR (container image built from engineers' code)`; `ECS on Fargate: image-processor service (runs the pre-written code · idempotent on image_id · autoscales on queue depth, Spot + On-Demand floor)`
- Analytics: `Glue Data Catalog (partition projection on dt)`; `Amazon Athena (serverless SQL, workgroup limits)`; `Amazon QuickSight (direct query, no SPICE cache)`; `Analysts (read-only IAM role)`
- Compliance: `Compliance sweeper — EventBridge (nightly) → Lambda — hard-deletes anything > 7 d, emits objects_older_than_7d`; `CloudTrail + S3 access logs (deletion audit) · CloudWatch alarms · Terraform (all retention as code)`

**Edges (label text in quotes; style in brackets)**
1. Web app → API Gateway "① request upload"
2. API Gateway → Lambda presign
3. Lambda presign → DynamoDB "PENDING row" [blue]
4. Web app → S3 raw "② PUT via presigned URL (bytes never touch API)" [purple]
5. Kafka web app → S3 raw "writes image (claim-check)" [purple]
6. Kafka web app → Kafka "publishes event"
7. Kafka → Kafka Connect
8. Kafka Connect → S3 metadata "events as JSON" [orange]
9. S3 raw → SQS "S3 ObjectCreated" [orange]
10. SQS → ECS "poll"
11. ECR → ECS "image" [dashed]
12. ECS → S3 processed "outputs" [blue]
13. ECS → S3 metadata "metadata row" [blue]
14. ECS → DynamoDB "DONE + expires_at" [blue]
15. S3 metadata → Glue → Athena → QuickSight → Analysts (four solid edges)
16. Athena → S3 metrics "nightly CTAS" [dashed, green]
17. Sweeper → S3 raw "delete > 7 d" and Sweeper → DynamoDB "delete expired" [dashed, red]; add one dashed red edge from Sweeper to the Storage container border labelled "lifecycle/TTL backstop on all stores"
18. Sweeper → CloudTrail/audit [dashed, red]

**Annotations**
- A small callout beside the Storage container: `S3 lifecycle: Expiration 7 d per prefix · versioning off · DynamoDB TTL · Kafka retention.ms = 7 d · Athena results 1 d · no SPICE`.
- A legend in the bottom-left corner: solid = data flow, dashed = control/deployment, red dashed = deletion.

---

### Checkpoints

#### Checkpoint 1: Skeleton
- Read `README.md` §3–§5. Create the page, the six swimlanes, the footer and the legend with the exact titles above, laid out on a grid. No nodes yet.
- Export PNG. **[STOP — WAIT FOR GREEN LIGHT]**

#### Checkpoint 2: Nodes
- Add every node listed above inside its container with the correct AWS4 shape, colour family and two-tier label. Align nodes within each container on a consistent grid (left-to-right in flow order; top-to-bottom for the vertical Analytics stack).
- Export PNG. **[STOP — WAIT FOR GREEN LIGHT]**

#### Checkpoint 3: Edges & annotations
- Add all edges with orthogonal routing and waypoints so that no edge passes through a node and crossings are minimised. Apply the colours/dash styles listed. Add the two annotations.
- Export PNG. **[STOP — WAIT FOR GREEN LIGHT]**

#### Checkpoint 4: Reconciliation & export
- Diff the diagram against `README.md`: every node in the diagram must be explained in §4; every component named in §4 and every row in the §5 purge table must be represented (node, annotation or edge). List any mismatches and fix the diagram — do **not** rewrite the README's design; if a genuine gap exists in the README, propose the one-line addition and wait.
- Export the final `architecture.png` (≥ 2000 px wide, white background, 20 px border) and save `architecture.drawio` uncompressed (plain XML, not base64) so it diffs cleanly in git.
- Report: node count, edge count, and the list of README sections each container corresponds to.
- **[STOP — WAIT FOR GREEN LIGHT]**
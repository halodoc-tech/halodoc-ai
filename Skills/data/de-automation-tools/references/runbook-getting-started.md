# Getting Started — de-automation-tools

A plain-language guide for new team members. Explains what each component does, why it exists,
and what happens end-to-end when you run it.

---

## The Big Picture

The `de-automation-tools` repository is a collection of five automation scripts that handle
repetitive Data Engineering tasks at Halodoc. Instead of manually configuring AWS services,
querying databases, or writing SQL by hand, these tools do it for you via Jenkins jobs.

```
                          ┌─────────────────────────────────────────────┐
                          │              de-automation-tools             │
                          │                                              │
  RDS MySQL  ──[DMS]────► │  dms_automation        → S3 raw data        │
                          │  transactional_migration → Hudi tables       │
  Google     ─────────► │  gsheet_onboarding     → S3 + Glue           │
  Sheets                  │                                              │
                          │  cost_tracker          → MySQL metrics DB    │
                          │  airflow_monitoring    → Google Chat / Slack │
                          └─────────────────────────────────────────────┘
```

---

## Component 1 — Airflow Monitoring

### What problem does it solve?

MWAA (the managed Airflow service) can become unhealthy silently — the scheduler stops, a DAG
fails to import, or a component crashes — and no one notices until pipelines start missing SLAs.
This tool checks health proactively and fires alerts.

### What does it do?

Runs on a schedule. Every run:
1. Calls the MWAA REST API to check if `Metadatabase`, `Scheduler`, `Triggerer`, and
   `Dagprocessor` are all healthy
2. Checks for any DAG import errors created in the last hour
3. If anything is unhealthy: **waits 60 seconds**, then checks again
4. If the issue is still there after the re-check: fires an alert to **Google Chat**
   (`datalake-prod-alerts` channel)

The 60-second re-check prevents false-positive alerts for transient blips.

### Example scenario

> The Airflow scheduler becomes unhealthy at 03:00.
> 03:01 — first check detects unhealthy scheduler
> 03:02 — re-check: still unhealthy
> 03:02 — alert fires to Google Chat
> On-call engineer sees the alert and restarts the scheduler

### No Jenkins trigger needed

This runs automatically. No manual parameters. If you need to debug why an alert fired, check:
- MWAA console for component status
- `GET /api/v2/importErrors` for bad DAG files

---

## Component 2 — Cost Tracker

### What problem does it solve?

Understanding what DE infrastructure actually costs week-over-week and how it's performing
(DAG success rate, Spark job efficiency, Redshift usage) requires pulling data from a dozen
different AWS services. This tool consolidates it all automatically.

### What does it do?

Runs every week (Saturday night → Sunday). Automatically calculates the **prior full week**
(Sunday to Saturday). For that window it collects:

| What | From |
|---|---|
| AWS costs per service (S3, Redshift, EMR, etc.) | Cost Explorer — filtered by `CostCenter: DE` tag |
| S3 bucket sizes + object counts | CloudWatch |
| S3 API call counts | CloudWatch |
| Redshift CPU + disk utilisation | CloudWatch |
| Redshift query duration breakdown (Short/Medium/Long) | Direct Redshift SQL |
| MWAA CPU + memory utilisation | CloudWatch |
| DAG success rate (%) | MWAA REST API |
| Spark job metrics (memory, cores, OOM count, etc.) | MySQL `spark_app_metrics` |

All metrics are inserted into `datalake_config.de_metrics` with columns:
`run_date · environment · category · service_name · metric_name · metric_value`

### Example scenario

> Every Monday morning, the DE manager opens a gsheet showing last week's costs and performance metrics. The data is there automatically — the cost tracker ran Monday morning.
> This week: Spark OOM task count spiked. The team investigates an inefficient job.

### Jenkins job

`WeeklyCostTrackerAutomation` — **no parameters, no manual trigger needed.** Runs automatically.
You can trigger it manually if you need a re-run (e.g., after a credential rotation).

---

## Component 3 — DMS Automation

### What problem does it solve?

Before any RDS MySQL data can be queried in the datalake, AWS DMS must be configured to
continuously replicate that data to S3. Setting up DMS endpoints, connection tests, and
replication tasks manually is error-prone and requires knowing many ARN IDs. This tool
automates the entire setup.

### What does it do?

Given a schema name and source DB details, it:
1. Checks if a DMS endpoint for this schema already exists (skip if yes)
2. Creates a **source endpoint** (the RDS MySQL database)
3. Tests the connection (300-second timeout)
4. Creates a **full-load replication task** — copies all current data from every table in the schema to S3
5. Creates an **incremental (CDC) replication task** — continuously replicates ongoing changes to S3

Every table gets an `ar_h_change_seq` column added (transformation rule) so downstream CDC
processing can track change order.

### Example scenario

> The `h4d_affiliate` RDS MySQL schema needs to be in the datalake.
> Engineer runs `DMSAutomation` with:
>   SCHEMA_NAME = h4d_affiliate
>   SOURCE_DB_HOST = bintan-analytics.clsqkkbd9zef...rds.amazonaws.com
>
> After the job:
> - DMS endpoint `src-h4d-affiliate` is created and connection-tested
> - Full-load task copies all `affiliate_products`, `doctor_referrals`, etc. to S3
> - Incremental task watches the MySQL binlog and streams new changes to S3 continuously
>
> Next step: run `TransactionTableOnboarding` to register these tables in the Hudi pipeline.

### Jenkins job

`DMSAutomation` — **always check `datalake_config.rds_endpoints` via Metabase (DB 41) first.**
If the schema is already there, no action needed.

---

## Component 4 — GSheet Onboarding

### What problem does it solve?

Many business teams maintain data in Google Sheets that analysts need to query alongside
warehouse data. Getting a sheet into the datalake requires: registering it in the config DB,
updating the Glue crawler to know about the new S3 location, and triggering the ingestion DAG.
This tool automates all three steps.

### What does it do?

Two modes:

**`new-table`** (first-time onboarding):
1. Validates the sheet isn't already registered
2. INSERTs a new row into `datalake_config.gsheet_export` with the sheet's S3 target path
3. Adds the new S3 path to the Glue crawler's target list
4. **Runs the Glue crawler** to discover the new schema
5. Triggers the `gsheet_migration_by_sheet_range_dag` Airflow DAG to ingest the sheet data

**`new-column`** (adding columns to an existing sheet):
1. Updates the `sheet_range` for the existing sheet (e.g., extend from `Sheet1!A:Z` to `Sheet1!A:AA`)
2. Triggers the DAG — no crawler update needed

### Example scenario

> The Finance team has a Google Sheet with budget allocations: Sheet ID `1BxiM...`, range `Sheet1!A:H`.
>
> DE engineer runs GSheet Onboarding (new-table):
> - Row inserted: `gsheet_export` now knows this sheet → S3 bucket `halodoc-datalake-prod-raw/gsheets/budget/`
> - Glue crawler updated to include the new S3 path
> - Crawler runs → schema registered in Glue catalog
> - DAG triggered → sheet data lands in S3
>
> Analysts can now query `budget` in Athena.
>
> Two weeks later, Finance adds a new column. DE runs onboarding again with `new-column`:
> - Sheet range updated in `gsheet_export`
> - DAG re-triggered — no crawler needed
> - New column available in Athena automatically

---

## Component 5 — Transactional Table Migration

### What problem does it solve?

After DMS is replicating an RDS schema to S3, Airflow still doesn't know those tables exist.
The Hudi pipeline needs metadata in `transformation_master` (column definitions, incremental keys,
schedule, job group, etc.) before it can create and maintain Hudi tables. Writing this metadata
by hand for every table in a schema is tedious and error-prone.

### What does it do?

Three modes:

**`new-table`** (first-time registration):
1. Validates each table isn't already in `transformation_master`
2. Introspects column definitions from `INFORMATION_SCHEMA` on the source RDS
3. Maps MySQL types to Hudi/Parquet types (e.g., `varchar` → `string`, `bigint` → `long`)
4. Scales up the DMS replication instance (`dms.t3.small` → `dms.t3.large`) for the load
5. Adds the new tables to the existing DMS replication task's table mapping rules
6. Restarts the replication task
7. INSERTs rows into `transformation_master` and `watermark` with status `pending`
8. Scales the instance back down
9. Triggers `load_raw_to_process_full_load_eks_dag` on MWAA

**`new-column-with-full-load`** (adding columns + re-ingesting data):
- Same DMS + DAG steps as new-table
- UPDATEs `tgt_schema_definition` in `transformation_master` and sets `status='ready'`

**`new-column-without-full-load`** (schema update only, no re-ingestion):
- Only UPDATEs `tgt_schema_definition` in `transformation_master`
- No DMS modification, no DAG trigger

### Example scenario

> After `DMSAutomation` is running for `h4d_affiliate`, the tables are landing in S3 as raw Parquet.
> But Airflow doesn't know to process them yet.
>
> DE engineer runs `TransactionTableOnboarding`:
>   SCHEMA_NAME  = h4d_affiliate
>   TargetDbName = h4d_affiliate
>   TableNames   = affiliate_products,doctor_referrals,doctor_referral_orders
>   ExecutionMethod = new-table
>
> After the job:
> - `transformation_master` now has rows for all 3 tables with their column schemas
> - DMS task is restarted with the new tables included
> - `load_raw_to_process_full_load_eks_dag` runs → Hudi tables created in the datalake
>
> Analysts can now query `h4d_affiliate.affiliate_products` as a Hudi table.
>
> A month later, a new column is added to `doctor_referrals` in RDS.
> Engineer runs `TransactionTableOnboarding` again:
>   ExecutionMethod = new-column-with-full-load
>   TableNames      = doctor_referrals
> → Column appears in the Hudi table after the next DAG run.

---

## End-to-End Flow: Onboarding a New RDS Schema

Here's how the tools connect for the most common task — getting a new RDS MySQL schema into
the datalake as queryable Hudi tables:

```
Step 1 — DMS Automation (DMSAutomation)
  ↓ Creates DMS endpoints + replication tasks
  ↓ Data from RDS starts landing in S3 (raw Parquet)

Step 2 — Transactional Migration (TransactionTableOnboarding)
  ↓ Registers table metadata in transformation_master
  ↓ Triggers full-load DAG
  ↓ Hudi tables created + maintained by Airflow

Step 3 — (ongoing) DMS replicates changes → Airflow incremental DAG updates Hudi tables
```

Steps 1 and 2 are one-time setup per schema. After that, DMS + Airflow handle everything
automatically.

---

## Quick Reference: Which Tool for Which Task?

| Situation | Tool |
|---|---|
| New RDS schema needs to be in the datalake | **DMS Automation** first, then **Transactional Migration** |
| Adding new tables from an already-onboarded RDS schema | **Transactional Migration** (`new-table`) |
| Adding new columns to an already-onboarded table | **Transactional Migration** (`new-column-with-full-load` or `new-column-without-full-load`) |
| Google Sheet data needs to be queryable in Athena | **GSheet Onboarding** (`GsheetIngestionAutomation`, `new-table`) |
| Sheet has a new column / expanded range | **GSheet Onboarding** (`GsheetIngestionAutomation`, `new-column`) |
| MWAA health check or alerting is broken | **Airflow Monitoring** — check the tests and alert channels |
| Weekly DE cost/metrics are missing | **Cost Tracker** — check if `WeeklyCostTrackerAutomation` ran |
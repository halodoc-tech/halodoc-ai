---
name: de-automation-tools
description: >
  Use when working in the de-automation-tools repo or asked about HaloDoc DE automation pipelines.
  "Transactional table" here means RDS (MySQL) → S3 via DMS, readable by Athena — NOT datamart/Redshift.
  Use when the user mentions: "onboard transactional table", "migrate rds table", "rds to s3",
  "rds via dms", "add column to rds-migrated table", "add column to dms-migrated table",
  "TransactionTableOnboarding", "dms automation", "dms endpoint",
  "dms replication task", "DMSAutomation", "setup dms for schema", "onboard schema to dms",
  "gsheet onboarding", "onboard google sheet", "GsheetIngestionAutomation", "add new sheet",
  "update sheet range", "cost tracker", "WeeklyCostTrackerAutomation", "de metrics",
  "airflow monitoring", "mwaa monitoring", "mwaa health check", "de-automation-tools",
  "de automation tools".
  Also use for Jenkins parameters, understanding a component, or onboarding as a new team member.
  DO NOT use for: creating datamart tables or adding columns to Redshift tables — use
  create-datamart-table or add-datamart-column skills instead.
---

# de-automation-tools

Data Engineering assistant at Halodoc. Route requests to the correct component, run pre-checks
via Metabase MCP, and output copy-paste-ready Jenkins parameters.

## Skill disambiguation

| Intent | Correct skill |
|---|---|
| Onboard RDS (MySQL) table → **S3 via DMS** (Athena-readable) | **this skill** — `TransactionTableOnboarding` |
| Add column to a DMS-migrated **Athena** table | **this skill** — `TransactionTableOnboarding` (`new-column-*` execution method) |
| Create a new **datamart** table (Athena → Redshift, or Redshift → Redshift) | `create-datamart-table` skill |
| Add column to an existing **Redshift** table | `add-datamart-column` skill |
| Set up DMS replication endpoint or task | **this skill** — `DMSAutomation` |
| Onboard a Google Sheet to the datalake | **this skill** — `GsheetIngestionAutomation` |

## Tools

| Tool | Used for |
|---|---|
| **Metabase MCP** (datalake-config-prod, DB ID 41) | Pre-checks · cost week reference · gsheet/table validation · `de_metrics` queries |
| **AWS MCP** (`mcp__awslabs-aws-api__call_aws`) | Cost Explorer USAGE_TYPE attribution · DMS task inspection — optional enrichment |

## Reference files

| File | Component | Load when |
|---|---|---|
| `references/runbook-transactional-migration.md` | TransactionTableOnboarding | User asks to onboard an RDS table to S3 via DMS (Athena-readable), or add a column to a DMS-migrated Athena table |
| `references/runbook-dms-automation.md` | DMSAutomation | User asks to set up DMS, create an endpoint, or modify a replication task |
| `references/runbook-gsheet-onboarding.md` | GsheetIngestionAutomation | User asks to onboard a Google Sheet or update a sheet range |
| `references/runbook-cost-tracker.md` | WeeklyCostTrackerAutomation | User asks about DE costs, week-over-week changes, or what drove an increase |
| `references/runbook-airflow-monitoring.md` | Airflow Monitoring | User asks about MWAA health, DAG success rates, or airflow monitoring alerts |
| `references/runbook-getting-started.md` | All components | User is new to the repo or asks what each component does |

## Workflow

1. **Identify component** from the request → load the matching runbook above
2. **Run Metabase MCP pre-checks** as described in the runbook (mandatory for gsheet and transactional migration; use for cost tracker to get week boundaries)
3. **Collect parameters** — ask only for what the runbook requires for the chosen execution method
4. **Output Jenkins copy-paste block** — use the exact template from the runbook

## Key rules

- **"Transactional table" = RDS → S3 via DMS** — DMS replicates RDS (MySQL) to S3; Athena queries that S3 data. This skill does NOT touch Redshift or datamart tables
- **"Add column to migrated table" = Athena table (DMS-migrated from RDS)** — if the user says "add column" without specifying, confirm whether the table is an Athena table migrated via DMS (this skill) or a Redshift table (redirect to `add-datamart-column`)
- **Datamart tables are out of scope** — Athena → Redshift (DWH/fact/dim) and Redshift → Redshift (presentation/mart) are handled by `create-datamart-table`; adding columns to any Redshift table is handled by `add-datamart-column`
- **Active-record filter** — always apply when querying datalake config tables via Metabase MCP: `dag_variable` → `is_active = 'Y'`; `dimensional_model` and `transformation_master` → `active_flag = 'Y'`
- **Pre-checks are mandatory** — for gsheet onboarding and transactional migration, always query Metabase MCP before generating a Jenkins config; the runbook specifies what to check
- **`new-column-*` (transactional migration)** — only 5 params needed (`Environment`, `ExecutionMethod`, `SchemaName`, `TargetDbName`, `TableNames`); do NOT ask for `JobGroup`, `Frequency`, `PartitionColumn`, or `IncrementalKey`
- **Cost questions** — always determine week boundaries first (Step 1 in runbook); service-level diffs come from `de_metrics`; USAGE_TYPE attribution requires AWS MCP
- **Jenkins job names are exact**: `TransactionTableOnboarding` · `DMSAutomation` · `GsheetIngestionAutomation` · `WeeklyCostTrackerAutomation`
- **Stage before Prod** — always remind the user to run stage first for transactional migration and gsheet onboarding
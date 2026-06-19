# Prerequisites — de-automation-tools

Routes DE-automation requests (DMS onboarding, gsheet ingestion, cost tracker,
airflow monitoring) and **generates Jenkins parameters**. Jenkins jobs do the work.

## What you must have

| Requirement | Why | If you don't have it |
|---|---|---|
| **Jenkins jobs** `TransactionTableOnboarding`, `DMSAutomation`, `GsheetIngestionAutomation`, `WeeklyCostTrackerAutomation` | Consume the generated params | Skill still emits the param block; apply manually |
| **AWS DMS** + **S3** + **Athena** | RDS→S3 replication; Athena reads the S3 data | Transactional-migration path is N/A without DMS |
| **HashiCorp Vault** at `vault_path_pattern` | DMS source-DB creds | Supply creds another way |
| **MWAA** (managed Airflow) | airflow-monitoring + cost DAG-run metrics | Monitoring path N/A |
| Either **datalake_config** (Metabase MCP) **or** `backend.mode: none` | rds_endpoints lookup, gsheet/table validation, `de_metrics`, cost weeks | Set `backend.mode` in `config.yml` |

## Configure first

1. Fill `config.yml` placeholders: region, DMS account ids, Vault path pattern, Redshift cluster, Jenkins job names, Metabase DB id.
2. Set `backend.mode`:
   - `datalake_config` — run live pre-checks via Metabase MCP.
   - `none` — skip live pre-checks; the skill asks you to supply/confirm values manually.

## Run the code

The runnable, config-driven source for all five components lives in [`src/`](src/) —
see [`src/README.md`](src/README.md) for install, the env vars to set, and how to run
each component. Every component reads `config.yml`, so once you fill it the code runs
from your machine (`python main.py`); no Jenkins required.

## Honest scope

This is the **most AWS-coupled** skill — it orchestrates DMS, MWAA, Vault, and Athena.
The bundled `src/` is fully generic (no hard-coded hosts/accounts/buckets) but still
assumes an AWS data-lake stack. Cost tracker is a simplified version: AWS Cost Explorer
spend per service for the previous week, optionally filtered by a `CostCenter` tag.

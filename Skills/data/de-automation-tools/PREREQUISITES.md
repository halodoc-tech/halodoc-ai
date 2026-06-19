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
| Registry: **`backend.mode: yaml`** (default) **or** `datalake_config` | dms/gsheet/transactional state (endpoints, sheets, onboarded tables) | `yaml` uses local files in `registry/` — no DB needed |

## Configure first

1. Fill `config.yml` placeholders: `<aws_region>`, DMS account ids, Vault base URLs, Jenkins job names.
2. Set `backend.mode`:
   - `yaml` (default) — state in local YAML files (`registry/`); no database. AWS actions still run.
   - `datalake_config` — original internal mode; reads/writes a MySQL metadata DB.

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

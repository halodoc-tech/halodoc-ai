# de-automation-tools — source

Generic, config-driven source for the five DE automation components. Clone the
repo, fill `../config.yml`, set the secret env vars, and run any component from
its own directory.

> The code reads **all** environment-specific values from `../config.yml` (the
> same file the skill documents). **No hostnames, account ids, ARNs, or bucket
> names are hard-coded.** Secrets (DB passwords, Vault tokens, AWS keys) are
> never stored in config — they come from environment variables.

## 1. Install

```bash
cd src
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure

Edit `../config.yml` and replace every `<...>` placeholder for your environment
(DB hosts, DMS endpoints/instances, Vault base URLs, Airflow env names, S3
bucket prefix, Redshift cluster, etc.).

By default each component finds `config.yml` by walking up from its own folder.
To point elsewhere, set `DE_CONFIG_PATH=/abs/path/to/config.yml`.

## 3. Secrets — environment variables

Set only what the component you run needs:

| Env var | Used by |
|---|---|
| `VAULT_STAGE_TOKEN`, `VAULT_PROD_TOKEN` | dms, transactional (fetch source DB creds from Vault) |
| `DATALAKE_CONFIG_STAGE_PASSWORD`, `DATALAKE_CONFIG_PROD_PASSWORD` | components writing to datalake_config |
| `AWS_ACCESS_KEY_ID_STAGE/_PROD`, `AWS_SECRET_ACCESS_KEY_STAGE/_PROD`, `AWS_SESSION_TOKEN_STAGE/_PROD` | cost_tracker (Cost Explorer / CloudWatch) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_REGION` | dms / transactional boto3 clients |

Component **inputs** (what to onboard) are also passed as env vars, matching the
original Jenkins parameters — e.g. `SCHEMA_NAME`, `SOURCE_DB_HOST`,
`SOURCE_DB_VAULT_PATH`, `TARGET_FULL_LOAD_ENDPOINT`, `GSHEET_ID`, `SHEET_RANGE`,
`BUSINESS_UNIT`, `JOB_GROUP`. See each component's runbook in `../references/`.

## 4. Run a component

Run from inside the component directory (imports are relative):

```bash
cd dms_automation                       && python main.py
cd transactional_table_migration_automation && python main.py
cd gsheet_onbording_automation          && python main.py
cd cost_tracker_automation              && python main.py
cd airflow_monitoring                   && python health_checker.py
```

## Notes

- **cost_tracker** is a simplified, generic version: it reports AWS Cost Explorer
  spend per service for the previous week (optionally filtered by a CostCenter tag).
  The original also collected S3/CloudWatch/Redshift inventory metrics — that part was
  dropped because it was tightly bound to one environment's bucket list. Extend
  `cost_by_service()` if you need more.
- These run standalone (`python main.py`) or under any scheduler/CI — the
  original deployment used Jenkins, but nothing here depends on Jenkins.

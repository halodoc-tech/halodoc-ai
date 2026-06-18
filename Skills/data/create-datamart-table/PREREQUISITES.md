# Prerequisites — create-datamart-table

This skill **generates Jenkins parameters** for onboarding a datamart table. The
Jenkins job is what actually creates the table — the skill only produces correct,
validated input for it. Read this before expecting it to work end-to-end.

## What you must have

| Requirement | Why | If you don't have it |
|---|---|---|
| **Jenkins jobs** `StageDatamartTableCreation` + `ProdDatamartTableCreation` (or your equivalents) | They consume the generated params and do the real DDL/registration | Skill still emits `redshift_ddl` + `rds_config` JSON you can apply by hand |
| **Source SQL in S3** at `s3://<script_bucket>/transformations/<schema>/<table>.sql` | Column types are inferred statically from this SQL | Paste the SQL when prompted instead |
| **Athena** access (for `dim_fact` / `monetization_dwh` / `report_layer` / `nrt_table`) | Source schema introspection (`DESCRIBE`) | Switch `backend.mode: yaml` and declare columns in `metadata.yml` |
| **Warehouse = Redshift** | DDL, distkey/sortkey, encoding rules are Redshift-specific | Other warehouses need the DDL templates ported |
| Either **datalake_config** (via Metabase MCP) **or** a `metadata.yml` | Table-exists / dependency / business_unit validation | Pick `backend.mode` in `config.yml` |

## Configure first

1. Copy `config.yml`, fill every `<...>` placeholder (buckets, region, Jenkins job names, Metabase DB ids).
2. Choose `backend.mode`:
   - `datalake_config` — you run Halodoc's metadata schema; skill validates live via Metabase MCP.
   - `yaml` — you don't; skill reads `metadata.yml` and skips live registry checks.
3. If your `datalake_config` table or column names differ, override them under `datalake_config:`.

## Honest scope

- **Fully portable for Halodoc-stack teams** — fill `config.yml` and go.
- **Partially portable elsewhere** — without the Jenkins jobs you get generated DDL/config as
  output but must apply it yourself. The taxonomy, encoding rules, and active-record filters are
  Redshift + datalake_config conventions; treat the runbooks as templates, not law.

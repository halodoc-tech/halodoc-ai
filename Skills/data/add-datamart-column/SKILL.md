---
name: add-datamart-column
description: >
  Adds new columns to an existing datamart table by generating the correct redshift_ddl
  and outputting ready-to-copy Jenkins parameters for ProdDatamartColumnAddition.

  Always use this skill when the user mentions any of:
  "add column", "new column to table", "add field to table", "add columns to existing table",
  "alter table add column", "tambahin kolom", "tambah kolom ke table", "add kolom baru".

  Also use when the user provides a table_name + column names and asks to generate Jenkins
  parameters, even if they don't say "add column" explicitly.
---

# Add Datamart Column

Data Engineering assistant. Generate correct, copy-paste-ready Jenkins parameters
for adding columns to existing datamart tables.

## Configuration — read first

**Load `config.yml` before anything else.** Environment-specific values (S3 bucket,
Metabase DB ids, region, Jenkins job names, table-type taxonomy, datalake_config
names) come from there. See `PREREQUISITES.md` for required backend.

`backend.mode` selects how the target table is confirmed:

- **`datalake_config`** — confirm table exists via Metabase MCP (`dimensional_model`).
- **`yaml`** — confirm against `metadata.yml` (existing columns listed there for
  duplicate detection); skip Metabase, warn that the check is manifest-only.

## Tools

| Tool | Used for |
|---|---|
| **AWS CLI** (`bash_tool`) | Fetch SQL from S3 (`aws.script_bucket`) · Athena DESCRIBE for source schema introspection |
| **Metabase MCP** (`metabase.redshift_db_id`) | Validate table existence · fetch existing DDL · check for duplicate columns. **Only when `backend.mode: datalake_config`.** |

## Reference files

| File | Purpose | Load when |
|---|---|---|
| `references/runbook-column-types.md` | Valid Redshift types + encoding rules | STEP 3 |
| `../create-datamart-table/references/runbook-source-type-analysis.md` | Athena→Redshift type mapping + SQL expression overrides | STEP 3 |

## Workflow (summary)

1. **Gather intent** — ask for: `table_name`, `table_type`, new column names (types auto-discovered)
2. **Fetch SQL from S3** — `s3://<datalake-script-bucket>/transformations/<schema>/<table_name>.sql`; try all schema folders before asking user
3. **Fetch existing DDL** — query `information_schema.columns` for the target table (validate exists + check for duplicates)
4. **Introspect source schemas** — AWS CLI Athena for `dim_fact` / `monetization_dwh` / `report_layer` / `nrt_table`; Metabase MCP for `presentations` / `monetization`
5. **Show SOURCE TYPE ANALYSIS** — display new columns with source→Redshift type mapping; resolve all `❓` before continuing
6. **Validate** — table exists in `dimensional_model`; new columns don't already exist in target
7. **Generate redshift_ddl** — flat JSON `{ "col": "type" }` — no `schema` wrapper, no distkey/sortkey
8. **Output Jenkins parameters** — show VALIDATION SUMMARY + copy-paste block; remind to run `StageDatamartColumnAddition` first, then `ProdDatamartColumnAddition`

## Key rules

- **Active-record filter** — when `backend.mode: datalake_config`, apply the filters from `config.yml` `datalake_config.active_filter` (default: `dag_variable` → `is_active = 'Y'`; `dimensional_model` / `transformation_master` → `active_flag = 'Y'`)
- **Respect `backend.mode`** — never call Metabase MCP when mode is `yaml`; validate against `metadata.yml`
- `add-column` DDL is **flat JSON** — not nested under `schema` like create-table
- **Never run the ETL query** — infer types statically from SQL expressions + DESCRIBE / information_schema
- **ETL routing** — Athena MCP for `dim_fact` / `monetization_dwh` / `report_layer` / `nrt_table`; Metabase for `presentations` / `monetization`
- **Always run Stage first** — `StageDatamartColumnAddition` → then `ProdDatamartColumnAddition`
- If table doesn't exist → stop and suggest `create-datamart-table` skill instead

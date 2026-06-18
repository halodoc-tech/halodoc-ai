---
name: create-datamart-table
description: >
  Creates a new datamart table end-to-end at Halodoc: collects intent, fetches source SQL from S3,
  introspects source schemas via Athena or Redshift, generates validated redshift_ddl and rds_config,
  and outputs copy-paste-ready Jenkins parameters.

  Always use this skill when the user mentions any of:
  "create datamart table", "onboard new table", "new DWH table", "buat table baru di datamart",
  "create presentation table", "create fact table", "create dimension table", "onboard PL table",
  "new report layer table", "create monetization table", "mau bikin table", "daftarin table baru".

  Also use when the user provides a table_name + table_type and asks to generate Jenkins parameters,
  even if they don't say "create" explicitly.
---

# Create Datamart Table

Data Engineering assistant at Halodoc. Generate correct, copy-paste-ready Jenkins parameters
for onboarding new datamart tables.

## Tools

| Tool | Used for |
|---|---|
| **AWS CLI** (`bash_tool`) | Fetch SQL from S3 · Athena DESCRIBE for source schema introspection |
| **Metabase MCP** (datalake-redshift, DB ID 39) | Validate table existence · validate business_unit · validate dependencies · Redshift source schema introspection |

## Reference files

| File | Purpose | Load when |
|---|---|---|
| `references/pipeline.md` | Full step-by-step workflow | Always — start here |
| `references/runbook-table-types.md` | rds_config templates + required keys per table_type | STEP 8 |
| `references/runbook-encoding-rules.md` | distkey / sortkey selection rules | STEP 7 |
| `references/runbook-validation-rules.md` | Validation checklist + common errors | STEP 4–6 |
| `references/runbook-source-type-analysis.md` | Type mapping: Athena→Redshift, SQL expression overrides, edge cases | STEP 3 |

## Key rules

- **Active-record filter** — always apply when querying datalake config tables via Metabase MCP: `dag_variable` → `is_active = 'Y'`; `dimensional_model` and `transformation_master` → `active_flag = 'Y'`

## Workflow (summary)

Read `references/pipeline.md` for the full procedure. At a high level:

1. **Gather intent** — ask only what cannot be auto-discovered (table_name, table_type, and conditionally: business_unit, schedule, dependency_type)
2. **Fetch SQL from S3** — infer schema folder from table_type + prefix; try all folders before asking user
3. **Introspect source schemas** — AWS CLI Athena for `dim_fact` / `monetization_dwh` / `report_layer` / `nrt_table`; Metabase MCP for `presentations` / `monetization`
4. **Confirm proposed config** — show auto-discovered values; wait for user approval before validating
5. **Validate** — table not in dimensional_model, business_unit, dependencies exist (all via Metabase MCP)
6. **Generate redshift_ddl** — column types from static SQL analysis; no encoding needed
7. **Generate rds_config** — use exact template for table_type; no extra keys
8. **Output Jenkins parameters** — show VALIDATION SUMMARY + copy-paste block; remind to run `StageDatamartTableCreation` first, then `ProdDatamartTableCreation`

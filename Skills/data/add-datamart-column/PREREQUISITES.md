# Prerequisites — add-datamart-column

Generates Jenkins parameters for adding columns to an **existing** Redshift datamart
table. Jenkins does the `ALTER TABLE`; the skill produces validated input.

## What you must have

| Requirement | Why | If you don't have it |
|---|---|---|
| **Jenkins jobs** `StageDatamartColumnAddition` + `ProdDatamartColumnAddition` | Apply the generated add-column DDL | Skill still emits the flat `{col: type}` DDL to apply by hand |
| **Source SQL in S3** at `s3://<script_bucket>/transformations/<schema>/<table>.sql` | New column types inferred statically from SQL | Paste the SQL when prompted |
| **Athena** access (athena-introspected table types) | `DESCRIBE` for source column types | Use `backend.mode: yaml` + declare types in `metadata.yml` |
| Either **datalake_config** (Metabase MCP) **or** `metadata.yml` | Confirm the target table exists + detect duplicate columns | Set `backend.mode` in `config.yml` |

## Configure first

1. Fill `config.yml` placeholders (bucket, region, Jenkins job names, Metabase DB ids).
2. Set `backend.mode` (`datalake_config` for live checks, `yaml` for self-contained).

## Notes

- add-column DDL is **flat JSON** `{ "col": "type" }` — no `schema` wrapper, no distkey/sortkey.
- Type mapping reuses `../create-datamart-table/references/runbook-source-type-analysis.md`.
- If the table does not exist → use the `create-datamart-table` skill instead.

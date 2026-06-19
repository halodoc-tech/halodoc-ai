# Pipeline: Create Datamart Table — Full Procedure

---

## STEP 1 — Gather intent (one-shot)

Ask only what cannot be auto-discovered. Collect in **one message**.

| Field | Ask when | Notes |
|---|---|---|
| `table_name` | Always | lowercase, underscores, e.g. `fact_doctor_consultations` |
| `table_type` | Always | `dim_fact` · `dim_fact_new_dag` · `presentations` · `monetization` · `monetization_dwh` · `report_layer` · `nrt_table` |
| `business_unit` | `dim_fact`, `dim_fact_new_dag`, `monetization_dwh` only | |
| `schedule` | `presentations`, `monetization`, `report_layer`, `nrt_table`, `dim_fact_new_dag` | Ask in WIB — convert to UTC internally |
| `dependency_type` | `presentations`, `monetization` only | `strong` or `weak` |

**Do NOT ask upfront** — auto-discovered from SQL:
- Columns + data types · `incremental_key` · `business_key` · `table_dependencies`

**Defaults (never ask unless user overrides):**
`queue_group=g0` · `business_key_allow_duplicates=0` · `uniqueness_columns_if_allow_duplicates=NULL`
`cross_dependency=no` (except `presentations`/`monetization` + `dependency_type=strong` → `yes`)

---

## STEP 2 — Fetch SQL from S3

```bash
aws s3 cp s3://<datalake-script-bucket>/transformations/<schema>/<table_name>.sql - \
  --region <aws_region>
```

Infer `<schema>` from table_type + table name prefix:

| table_type | prefix | schema folder |
|---|---|---|
| `dim_fact`, `dim_fact_new_dag` | `fact_` | `facts` |
| `dim_fact`, `dim_fact_new_dag` | `dim_` | `dimensions` |
| `presentations` | any | `presentations` |
| `monetization` | any | `monetization` |
| `monetization_dwh` | `fact_` | `monetization_facts` |
| `monetization_dwh` | `dim_` | `monetization_dimensions` |
| `report_layer`, `nrt_table` | any | `reports` |

Try all schema folders silently before asking. If still not found, ask once:
1. Correct S3 path · 2. Local file path · 3. Paste SQL · 4. Skip → conservative defaults

---

## STEP 3 — Parse SQL + introspect source schemas

### 3a — Extract from SQL

- **Columns** — each aliased SELECT expression
- **incremental_key** — `updated_at` if present; else `created_at`; else flag for user
- **business_key** — most specific primary ID column
- **table_dependencies** — all `schema.table` from FROM/JOIN (exclude CTEs + subquery aliases)

### 3b — Introspect source schemas

Which tool depends on ETL pattern:

| table_type | Source | Tool |
|---|---|---|
| `dim_fact`, `dim_fact_new_dag`, `monetization_dwh`, `report_layer`, `nrt_table` | Athena | **AWS CLI** |
| `presentations`, `monetization` | Redshift | **Metabase MCP** |

> Never run the ETL query. Use DESCRIBE (Athena) or `information_schema` (Redshift) only.

**AWS CLI — Athena DESCRIBE** (run all source tables in parallel):

If the user's `sso_role_name` is `bi-prod`, add `--work-group bi-prod` to the command.
If the default workgroup returns an access error, retry with `--work-group bi-prod`.

```bash
# default workgroup (try first)
aws athena start-query-execution \
  --query-string "DESCRIBE <database>.<table>" \
  --result-configuration "OutputLocation=s3://<athena-results-bucket>/schema-check/" \
  --region <aws_region>

# if access error — retry with bi-prod workgroup
aws athena start-query-execution \
  --query-string "DESCRIBE <database>.<table>" \
  --result-configuration "OutputLocation=s3://<athena-results-bucket>/schema-check/" \
  --work-group bi-prod \
  --region <aws_region>
```

```bash
aws athena get-query-results --query-execution-id <id> --region <aws_region>
```

**Metabase MCP — Redshift information_schema**:
```sql
SELECT column_name, data_type, character_maximum_length, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_schema = '<source_schema>' AND table_name = '<source_table>'
ORDER BY ordinal_position
```

For type mapping rules and edge cases (SUM overflow, binary columns, Unix timestamps),
see `runbook-source-type-analysis.md`.

### 3c — Show SOURCE TYPE ANALYSIS

Present before generating DDL. Resolve all `❓` before continuing.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOURCE TYPE ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Column         Source table.column        Source type   → Redshift type   Note
order_id       oms.orders.id              bigint        → bigint          ✅
total_amount   oms.orders.amount (SUM)    decimal(10,2) → decimal(18,2)   ⚠️ widened
doc_content    docs.content               string        → varchar(?)      ❓ confirm size
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 3d — Confirm proposed configuration

Show all auto-discovered and defaulted values. Wait for user approval before proceeding.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROPOSED CONFIGURATION — please confirm or correct
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Source SQL          : facts/fact_prescription_upload.sql ✅ found
incremental_key     : updated_at                         (auto)
business_key        : prescription_upload_id             (auto)
table_dependencies  : [dwh.dim_user, dwh.dim_product]    (from SQL JOINs)
queue_group         : g0                                 (default)
business_key_allow_duplicates : 0                        (default)
cross_dependency    : no                                 (default)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Anything to change? Reply "looks good" to continue.
```

---

## STEP 4 — Validate: table does not already exist

**Metabase MCP** (Redshift):
```sql
SELECT COUNT(*) FROM datalake_config.dimensional_model
WHERE tgt_table_name = '<table_name>'
  AND active_flag = 'Y'
```
Count > 0 → stop. Table exists. Suggest `add-datamart-column` skill.

---

## STEP 5 — Validate: business_unit

**Metabase MCP** (Redshift):
```sql
SELECT DISTINCT business_unit FROM datalake_config.dimensional_model
WHERE table_type = '<facts|dimensions>'
  AND active_flag = 'Y'
```
- `dim_fact` → must exist. Show valid list if not found.
- `dim_fact_new_dag` → must NOT exist. Warn and suggest `dim_fact` if it does.

---

## STEP 6 — Validate: dependencies exist

**Metabase MCP** (Redshift):
```sql
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = '<schema>' AND table_name = '<table>'
```
Missing → warn but do not block (user may be creating tables in order).

---

## STEP 7 — Generate redshift_ddl

No encoding in output — automation applies it. See `runbook-encoding-rules.md` for distkey/sortkey rules.

```json
{
  "schema": { "column_name": "data_type" },
  "distkey": "column_name",
  "sortkey": "col1,col2"
}
```

Warn if: varchar(n) < 50 for name/description fields · no timestamp column present.

---

## STEP 8 — Generate rds_config

Use the exact template from `runbook-table-types.md` for the table_type. **No extra keys.**

**table_dependencies format:**
```
# presentations / monetization — strong:  'is_skip_allowed': 'False'
# presentations / monetization — weak:    'is_skip_allowed': 'True'
# all other table_types:                  no is_skip_allowed key
```

**WIB → UTC:** `00:00→0 17 * * *` · `07:00→0 0 * * *` · `08:00→0 1 * * *` · `12:00→0 5 * * *`

---

## STEP 9 — Output Jenkins parameters

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ table_name: fact_doctor_consultations — new
✅ business_unit: telemedicine — found
✅ dependency dwh.dim_doctor — exists
⚠️  fee decimal(10,2) — confirm precision

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — copy into UI
Jobs: StageDatamartTableCreation → verify → ProdDatamartTableCreation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

table_name:        fact_doctor_consultations
table_type:        dim_fact
cross_dependency:  no

redshift_ddl:
  { "schema": { ... }, "distkey": "...", "sortkey": "..." }

rds_config:
  { ... }
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Remind user: run **StageDatamartTableCreation** first, verify, then **ProdDatamartTableCreation**.

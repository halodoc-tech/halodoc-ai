# Runbook: Source SQL & Type Analysis

Before generating `redshift_ddl`, always inspect the source ETL query to catch type mismatches
that would cause silent data loss, overflow errors, or broken incremental loads after onboarding.

---

## Step 1 — Find the source SQL

SQL scripts are stored centrally in S3. Fetch via AWS CLI (streams to stdout, no local download):

```bash
aws s3 cp s3://halodoc-datalake-prod-script/transformations/<schema>/<table_name>.sql - \
  --region ap-southeast-1
```

Infer `<schema>` from the table name prefix:

| table name prefix | schema folder |
|---|---|
| `fact_` | `facts` |
| `dim_` | `dimensions` |
| presentations tables | `presentations` |
| monetization tables | `monetization` |
| `monetization_dwh` with `fact_` prefix | `monetization_facts` |
| `monetization_dwh` with `dim_` prefix | `monetization_dimensions` |
| report/nrt tables | `reports` |

If not found at the inferred path, try the other schema folders before asking the user.

If still not found, ask the user **once** with these options:
1. Provide the correct S3 path
2. Provide a local file path
3. Paste the SQL query directly into the chat
4. Skip — proceed to Step 6 (conservative defaults, no source verification)

---

## Step 2 — Extract source tables and columns

From the SQL file, identify:
1. All **source tables** referenced in FROM / JOIN clauses
2. All **expressions** used for each output column (raw column, aggregation, cast, calculation)
3. Whether each column is a raw passthrough or a derived expression

---

## Step 3 — Fetch source information_schema via Metabase MCP

For each source table found in step 2:

```
Use datalake-redshift DB (Metabase MCP):
SELECT column_name, data_type, character_maximum_length, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_schema = '<source_schema>'
  AND table_name = '<source_table>'
ORDER BY ordinal_position
```

Build a mapping: `output_column → (expression, source_type)`.

---

## Step 4 — Apply type upgrade rules

Use the following rules to validate or override user-provided types:

### Aggregation overflow (most common issue)

| Source type | Expression | Recommended Redshift type | Reason |
|---|---|---|---|
| `integer` / `int4` | `SUM(col)` | `bigint` | Sum of many ints can exceed INT_MAX (2.1B) |
| `integer` / `int4` | `COUNT(*)` or `COUNT(col)` | `bigint` | Row counts on large tables overflow INT |
| `smallint` / `int2` | `SUM(col)` | `bigint` | Even faster overflow |
| `integer` | `AVG(col)` | `double precision` | Average loses precision as integer |
| `decimal(p,s)` | `SUM(col)` | `double precision` | Use double precision to avoid overflow and precision loss |
| `boolean` | `SUM(col)` | `integer` | Boolean cast to 0/1 sum |

### Byte arrays / binary columns

| Source type | Recommended action |
|---|---|
| `bytea`, `blob`, `binary`, `varbinary` | **Ask the user**: "This column is stored as binary data. Should it be cast to `varchar` (store as hex/base64), or do you want to cast it to `integer`/`bigint` in the query first?" |
| Column name ends in `_hash` or `_bytes` | Surface warning — likely binary |

### String sizing

| Source column | Rule |
|---|---|
| Source is `varchar(n)` | Use same `varchar(n)` — never smaller; only go larger if SQL expression can expand output |
| Source is `char(n)` fixed | Use `varchar(n)` (Redshift pads fixed char) |
| Column name is UUID-like (id, entity_id, patient_id…) | `varchar(36)` |
| Column name is status/type/enum/channel | `varchar(50)`–`varchar(100)` — pick based on known max value length |
| Column name is name/reason/error/label/utm_* | `varchar(255)` |
| Column name is url/path | `varchar(500)` — URLs can be long but are bounded; do not default to MAX |
| Source is `text` or `varchar(MAX)` | Use `varchar(MAX)` only if source is genuinely unbounded (free text, JSON blobs, document content). **Ask the user** before applying MAX to any other column. |
| `CONCAT` / string operations | Estimate max output length from operands; use `varchar(n)` sized to that estimate, not MAX |
| `get_json_object(…)` result | `varchar(255)` unless the extracted value is known to be long — confirm with user |
| `to_json(…)` / large JSON arrays | `varchar(MAX)` acceptable here — output is genuinely unbounded |

### Timestamp handling

| Source type | Recommended Redshift type |
|---|---|
| `datetime` (MySQL) | `timestamp` |
| `date` only | `date` (not timestamp, unless you need time component) |
| Unix epoch integer | Warn user: "This looks like a Unix timestamp. Should it be stored as `timestamp` after conversion, or kept as `bigint`?" |

### Other patterns

| Pattern | Rule |
|---|---|
| `COALESCE(col, 0)` where col is nullable int | Type stays as source type, but note it's effectively NOT NULL after transform |
| `CASE WHEN ... THEN 1 ELSE 0` | Use `integer` (not `smallint`) |
| Division `/` on integers | Use `double precision` — integer division truncates |
| `DATEDIFF` result | Use `integer` for days, `bigint` for seconds |
| `CONCAT` or string operations | Use `varchar(n)` — size to maximum possible output length |

---

## Step 5 — Surface findings before generating DDL

Present a type analysis table showing your recommendations vs what the user provided (if they provided types):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOURCE TYPE ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Column               Source Type     Expression      Recommendation   Note
──────────────────────────────────────────────────────────────────────────
order_id             int4            passthrough     bigint           ✅ user provided bigint
total_amount         decimal(10,2)   SUM(amount)     decimal(18,2)    ⚠️  widened for sum
order_count          int4            COUNT(*)        bigint           ⚠️  COUNT needs bigint
doc_number           bytea           passthrough     varchar(?)       ❓ binary — needs decision
status               varchar(50)     passthrough     varchar(50)      ✅
created_at           timestamp       passthrough     timestamp        ✅
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

For any `❓` items, pause and ask the user before continuing.

---

## Step 6 — If no source SQL is available

If the user cannot provide a source SQL file, apply conservative defaults and warn:

- All numeric columns → default to `bigint` (not `integer`) to be safe
- All text columns → confirm varchar sizes are sufficient
- Add a warning in the output: "⚠️  Source SQL not verified — types are based on user input only. Please verify before running Prod."

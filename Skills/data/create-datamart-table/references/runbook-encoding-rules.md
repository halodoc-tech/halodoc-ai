# Runbook: Redshift Encoding Rules

Source of truth extracted from `src/datamart_module/query_builder.py:apply_encoding()`.

---

## Overview

When generating `redshift_ddl`, you do NOT need to specify encodings — the automation applies them automatically. Just specify the data type.

```json
{
  "schema": {
    "id": "bigint",
    "name": "VARCHAR(255)",
    "created_at": "timestamp"
  },
  "distkey": "id",
  "sortkey": "created_at"
}
```

The automation maps each type to its encoding internally. The table below shows what gets applied.

---

## Type → Encoding Map

| SQL Type | Encoding Applied | Notes |
|---|---|---|
| `bigint` | `az64` | |
| `integer` / `int` / `int4` | `az64` | Use `integer` not `int` — more explicit |
| `int2` / `smallint` | `az64` | |
| `int8` | `az64` | |
| `decimal` / `numeric` | `az64` | e.g., `decimal(10,2)` |
| `timestamp` | `az64` | |
| `timestamp without time zone` | `az64` | |
| `timestamp with time zone` / `timestamptz` | `az64` | |
| `date` | `az64` | |
| `time` / `timetz` | `az64` | |
| `varchar` / `VARCHAR` | `zstd` | e.g., `VARCHAR(255)`, `VARCHAR(MAX)` |
| `char` / `nchar` / `bpchar` / `nvarchar` | `zstd` | |
| `text` | `zstd` | |
| `boolean` / `bool` | `zstd` | |
| `float` / `float4` / `float8` | `zstd` | |
| `real` / `double precision` | `zstd` | |
| `super` | `zstd` | |

---

## distkey and sortkey

```json
{
  "distkey": "column_name",
  "sortkey": "col1,col2"
}
```

- `distkey`: Single column. Use the highest-cardinality column (usually the primary ID).
  - Also accepts `"auto"` to let Redshift decide automatically.
- `sortkey`: Comma-separated columns. Use the incremental key + frequently filtered columns.

### How to choose distkey

1. If the table has a primary ID that other tables JOIN on → use that ID
2. If the table is mostly scanned with date filters → use the date column
3. If unsure → use `"auto"` and Redshift will optimize

### How to choose sortkey

1. Always include `incremental_key` (the updated_at / created_at column)
2. Add any other commonly-filtered columns (e.g., `status`, `type`)
3. Order: most-filtered first

---

## Common Patterns

### Fact table columns
```json
{
  "schema": {
    "order_id": "bigint",
    "user_id": "bigint",
    "status": "VARCHAR(50)",
    "amount": "decimal(15,2)",
    "created_at": "timestamp",
    "updated_at": "timestamp"
  },
  "distkey": "order_id",
  "sortkey": "updated_at,created_at"
}
```

### Dimension table columns
```json
{
  "schema": {
    "doctor_id": "bigint",
    "doctor_name": "VARCHAR(256)",
    "specialty": "VARCHAR(128)",
    "is_active": "boolean",
    "created_at": "timestamp",
    "updated_at": "timestamp"
  },
  "distkey": "doctor_id",
  "sortkey": "updated_at"
}
```

---

## Notes

- The automation accepts both with and without encoding in input — you can omit encoding
- `VARCHAR(MAX)` is valid in Redshift (stores up to 65535 chars)
- Avoid using `INT` alone — prefer `integer` or `bigint` for clarity
- Always confirm varchar lengths are sufficient for source data (e.g., `VARCHAR(50)` may truncate names)

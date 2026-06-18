# Runbook: Column Types for Column Addition

---

## add-column DDL Format

Different from table creation — a flat JSON object (no nesting under `schema`):

```json
{
  "new_column_name": "data_type",
  "another_column": "data_type"
}
```

Do NOT include `distkey`, `sortkey`, or a `schema` wrapper.

---

## Valid Redshift Data Types

| Category | Types | Encoding (auto-applied) | Preferred |
|---|---|---|---|
| Integer | `bigint`, `integer`, `smallint`, `int2`, `int4`, `int8` | az64 | |
| Decimal / Floating point | `double precision`, `float`, `float4`, `float8`, `real`, `decimal(p,s)`, `numeric(p,s)` | zstd | **`double precision`** — use this for all `float8`, `decimal`, or `numeric` columns |
| Text | `varchar(n)`, `VARCHAR(MAX)`, `char(n)`, `text` | zstd |
| Timestamp | `timestamp`, `timestamptz` | az64 |
| Date/Time | `date`, `time`, `timetz` | az64 |
| Boolean | `boolean` | zstd |
| Semi-structured | `super` | zstd |

---

## Common Mistakes

| Mistake | Correct |
|---|---|
| `int` | `integer` or `bigint` |
| `string` | `varchar(n)` |
| `datetime` | `timestamp` |
| `float(53)`, `float8`, `decimal`, `numeric` | `double precision` |
| `number(10,2)` | `decimal(10,2)` |

---

## VARCHAR Size Guidelines

| Use case | Recommended size |
|---|---|
| Short codes, status flags | `varchar(50)` |
| Names, short descriptions | `varchar(256)` |
| Long descriptions, URLs | `varchar(512)` |
| Potentially very long text | `VARCHAR(MAX)` |

---

## Notes

- Automation auto-applies encoding — no need to specify `encode az64` in input
- `ALTER TABLE ADD COLUMN` in Redshift adds columns at the end of the table
- Columns cannot be removed once added — be certain before running on Prod
- Column names must be lowercase and use underscores (no spaces, no camelCase)

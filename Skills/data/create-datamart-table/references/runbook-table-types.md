# Runbook: Table Types Reference

Source of truth extracted from `src/datamart_module/validator.py` and ETL as Code wiki.

---

## DWH Layer Architecture

There are two parallel layer stacks, each with a base layer and a presentation layer:

**Core DWH stack:**
```
Athena/PySpark (source)
    → dwh (dim_fact / dim_fact_new_dag)          ← base facts & dimensions
        → presentations                            ← next layer, built on top of dwh
```

**Monetization stack:**
```
Athena/PySpark (source)
    → monetization_dwh (monetization_dwh)         ← base facts & dimensions for monetization
        → monetization                             ← next layer, built on top of monetization_dwh
```

**Key implications:**
- `presentations` and `monetization` are Redshift-to-Redshift ETL — their source is always a `dwh` or `monetization_dwh` table, not Athena. Use **Metabase Redshift MCP** for source schema introspection.
- `dim_fact`, `dim_fact_new_dag`, `monetization_dwh`, `report_layer`, `nrt_table` are Athena-to-Redshift ETL. Use **AWS CLI Athena MCP** for source schema introspection.
- Never create a `presentations` table that reads directly from Athena — it must go through `dwh` first.

---

## Table Type → Redshift Schema Mapping

| table_type | Redshift Schema | Who Creates |
|---|---|---|
| `dim_fact` | `dwh` | DE only |
| `dim_fact_new_dag` | `dwh` | DE only (new business unit) |
| `presentations` | `presentations` | BIA + DE |
| `monetization` | `monetization` | DE |
| `monetization_dwh` | `monetization_dwh` | Marketing Team |
| `report_layer` | `reports` | DE |
| `nrt_table` | `reports` | DE |

---

## Required rds_config Keys Per Table Type

### `presentations` and `monetization`

```json
{
  "schedule": "0 0 * * *",
  "incremental_key": "created_at",
  "business_key": "id",
  "dependency_type": "strong",
  "table_dependencies": "[{'table_name': 'dwh.fact_orders', 'is_skip_allowed': 'False'}]",
  "business_key_allow_duplicates": "0",
  "uniqueness_columns_if_allow_duplicates": "NULL"
}
```

**Rules:**
- `dependency_type`: must be `strong` or `weak`
- `schedule`: cron expression in **UTC** (e.g., 08:00 WIB = `0 1 * * *`)
- `cross_dependency`: set `yes` if `dependency_type` is `strong`; `no` if `weak`

---

### `dim_fact` (existing business unit — joins existing DAG)

```json
{
  "incremental_key": "order_updated_at",
  "business_key": "order_id",
  "table_dependencies": "[{'table_name': 'mai.order'}]",
  "table_type": "facts",
  "business_unit": "sales",
  "queue_group": "g0",
  "business_key_allow_duplicates": "0",
  "uniqueness_columns_if_allow_duplicates": "NULL"
}
```

**Rules:**
- `table_type`: must be `facts` or `dimensions`
- `business_unit`: must already exist in `datalake_config.dimensional_model` — validate via Metabase MCP
- `queue_group`: default `g0`; only change if user specifies otherwise
- `business_key_allow_duplicates`: default `"0"`
- `uniqueness_columns_if_allow_duplicates`: default `"NULL"`
- No `schedule` field for `dim_fact`

---

### `dim_fact_new_dag` (new business unit — creates a new DAG)

```json
{
  "schedule": "0 19,8 * * *",
  "incremental_key": "updated_at",
  "business_key": "order_item_id",
  "table_dependencies": "[{'table_name': 'oms.orders'}, {'table_name': 'oms.order_item'}]",
  "table_type": "facts",
  "business_unit": "operations",
  "queue_group": "g0",
  "business_key_allow_duplicates": "0",
  "uniqueness_columns_if_allow_duplicates": "NULL"
}
```

**Rules:**
- Same as `dim_fact` + requires `schedule`
- `business_unit`: must NOT already exist — this creates a new one

---

### `monetization_dwh`

```json
{
  "incremental_key": "order_status_codes_updated_at",
  "business_key": "order_status_codes_id",
  "table_dependencies": "[{'table_name': 'source_db.example_table'}]",
  "table_type": "dimensions",
  "business_unit": "marketing",
  "queue_group": "g0",
  "business_key_allow_duplicates": "0",
  "uniqueness_columns_if_allow_duplicates": "NULL"
}
```

---

### `report_layer` and `nrt_table`

```json
{
  "schedule": "0 19,8 * * *",
  "incremental_key": "updated_at",
  "business_key": "order_item_id",
  "table_dependencies": "[{'table_name': 'oms.orders'}, {'table_name': 'oms.order_item'}]",
  "business_key_allow_duplicates": "0",
  "uniqueness_columns_if_allow_duplicates": "NULL"
}
```

---

## table_dependencies Format

Always a **string** containing a Python-list-of-dicts:

```
"[{'table_name': 'schema.table', 'is_skip_allowed': 'False'}]"
```

- `table_name`: `schema.table` format — dot-separated
- `is_skip_allowed`: `'False'` = strong (must wait), `'True'` = weak (can skip)
- Forbidden schemas: `reference_table`, `adhoc_data`

is_skip_allowed is only for presentations and monetization schema
---

## business_key_allow_duplicates Values

| Value | Meaning |
|---|---|
| `"0"` | No duplicates allowed on business key |
| `"1"` | Duplicates allowed — must specify `uniqueness_columns_if_allow_duplicates` |

If `"1"`, set `uniqueness_columns_if_allow_duplicates` to the column(s) that define uniqueness (e.g., `"column_1_id, column_2_id"`).
If `"0"`, set `uniqueness_columns_if_allow_duplicates` to `"NULL"`.

---

## cross_dependency

| Value | DAG type created |
|---|---|
| `yes` | Listener DAG — has dependencies on other DAGs |
| `no` | Non-listener DAG — runs independently on schedule |

**Default rule:** Always use `no` unless overridden.

**Exception:** Set `yes` only for `presentations` or `monetization` table types when `dependency_type=strong`.

All other table types (`dim_fact`, `dim_fact_new_dag`, `monetization_dwh`, `report_layer`, `nrt_table`) always use `cross_dependency=no`.

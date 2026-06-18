# Transactional Table Migration Automation

Automates onboarding of RDS MySQL tables into the Hudi-based data lake. Generates INSERT/UPDATE
SQL for `transformation_master` and `watermark` tables, modifies and restarts DMS replication tasks,
and triggers the full-load Airflow DAG.

**Entry point:** `src/transactional_table_migration_automation/main.py`

---

## Jenkins Job — TransactionTableOnboarding

### Parameters

| Parameter | Type | Default | `new-table` | `new-column-*` | Notes |
|---|---|---|---|---|---|
| `Environment` | Choice | — | Required | Required | `stage` · `prod` |
| `ExecutionMethod` | Choice | — | Required | Required | `new-table` · `new-column-with-full-load` · `new-column-without-full-load` |
| `SchemaName` | String | — | Required | Required | Source RDS schema name |
| `TargetDbName` | String | — | Required | Required | Hudi target DB name |
| `TableNames` | String | — | Required | Required | Comma-separated table names |
| `PartitionColumn` | String | _(blank)_ | Optional | **Not needed** | Only for new-table; leave blank if no partition |
| `Frequency` | String | `360` | Optional | **Not needed** | Only for new-table; choose `30` / `360` / `1440` |
| `JobGroup` | String | `g6` | Optional | **Not needed** | Only for new-table; existing tables keep their job group |
| `IncrementalKey` | String | `updated_at` | Optional | **Not needed** | Only for new-table; CDC incremental column |

> **For `new-column-with-full-load` and `new-column-without-full-load`:** Only `Environment`, `ExecutionMethod`, `SchemaName`, `TargetDbName`, and `TableNames` are needed. Do NOT ask for `PartitionColumn`, `Frequency`, `JobGroup`, or `IncrementalKey` — the existing `transformation_master` record already holds those values and they are not updated.

### Jenkins Copy-Paste Block

**For `new-table`** (all parameters required):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — TransactionTableOnboarding
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  <stage | prod>

ExecutionMethod:
  new-table

PartitionColumn:
  <column_name or leave blank>

Frequency:
  <30 | 360 | 1440>

JobGroup:
  <g0 | g6 | ...>

IncrementalKey:
  <updated_at or other column>

TargetDbName:
  <target_db_name>

SchemaName:
  <schema_name>

TableNames:
  <table1,table2,table3>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**For `new-column-with-full-load` or `new-column-without-full-load`** (scheduling params not needed):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — TransactionTableOnboarding
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  <stage | prod>

ExecutionMethod:
  <new-column-with-full-load | new-column-without-full-load>

TargetDbName:
  <target_db_name>

SchemaName:
  <schema_name>

TableNames:
  <table1,table2,table3>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Example** (from `h4d_affiliate` schema):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — TransactionTableOnboarding
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  prod

ExecutionMethod:
  new-table

PartitionColumn:
  (leave blank)

Frequency:
  360

JobGroup:
  g6

IncrementalKey:
  updated_at

TargetDbName:
  h4d_affiliate

SchemaName:
  h4d_affiliate

TableNames:
  affiliate_product_audit,affiliate_products,doctor_referral_order_items,
  doctor_referral_orders,doctor_referral_performance_metrics,
  doctor_referral_products,doctor_referrals

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Execution Methods

| Method | DMS Modified | SQL Generated | DAG Triggered |
|---|---|---|---|
| `new-table` | Yes | INSERT into `transformation_master` + `watermark` | Yes |
| `new-column-with-full-load` | Yes | UPDATE `schema_definition`, set `status='ready'` | Yes |
| `new-column-without-full-load` | No | UPDATE `schema_definition` only | No |

---

## File Structure

```
src/transactional_table_migration_automation/
  main.py                        # Orchestrator + SQL generation
  configs/
    datalake_config_creds.py     # Stage/prod DB host/user
  sql_scripts/
    datalake_config.py           # All SQL templates (INSERT, UPDATE, SCHEMA_DEF, watermark)
  utils/
    api.py                       # DMS operations, DAG trigger via MWAA
    variables.py                 # Instance ARNs, DAG name, MWAA env names
```

---

## Key Functions

### `map_data_type(datatype)` — MySQL → Hudi/Parquet type mapping

| MySQL | Hudi/Parquet |
|---|---|
| `int`, `tinyint`, `smallint`, `mediumint` | `integer` |
| `bigint` | `long` |
| `float`, `double`, `decimal(...)` | `double` |
| `varchar`, `text`, `enum`, `set`, `char`, `json` | `string` |
| `date` | `date` |
| `datetime`, `timestamp` | `timestamp` |
| `bit` | `boolean` |

### `create_query(...)` — SQL generator

For each table in `table_list`:
1. Query `INFORMATION_SCHEMA.columns` for column definitions
2. Map each datatype using `map_data_type()`
3. Build `schema_doc` JSON: `{column_name: mapped_type}`
4. Generate INSERT or UPDATE SQL based on `execution_method`

### `dag_variable_enum_validator(cursor, field_name, value)`

Validates `frequency` and `job_group` exist in `datalake_config.dag_variable`.
Use this to prevent invalid config before INSERT.

---

## Orchestration Flow

```
1. Parse env vars (defaults: Frequency=360, JobGroup=g6, IncrementalKey=updated_at)
2. Connect to datalake-config DB
3. Validate frequency + job_group via dag_variable_enum_validator()
4. Get DMS task name from rds_endpoints
5. table_validator() → Remove already-onboarded tables

For new-column-without-full-load:
  → sql_generator() → UPDATE queries only
  → Execute UPDATEs on datalake-config
  → Done (no DMS, no DAG)

For new-table or new-column-with-full-load:
  → resize_replication_instance(scale='up')   [prod only]
  → describe_replication_task() → Get current table mappings
  → modify_replication_task() → Add new tables
  → restart_replication_task()
  → sql_generator() → INSERT + watermark SQL
  → Execute INSERTs on datalake-config
  → resize_replication_instance(scale='down') [prod only]
  → trigger_full_load_dag()
```

---

## transformation_master Columns Populated

```
src_dbname  tgt_dbname  src_schemaname  tgt_schemaname  src_tablename  tgt_tablename
src_s3_path  tgt_s3_path  src_incr_s3_path  key_column  precombine  incremental_key
tgt_partitionkey  tgt_loadtype  active_flag  status  tgt_schema_definition
add_source_header  source_header  is_transform  transform_logic
hudi_parallelism  frequency_in_mins  job_group  clustering_enabled  enable_hudi_index
```

**`status` values:** `'pending'` (new-table) · `'ready'` (new-column-with-full-load)

---

## DMS Configuration (`variables.py`)

| Setting | Value |
|---|---|
| `migration_type` | `full-load` |
| `upscale_instance_class` | `dms.t3.large` |
| `down_instance_class` | `dms.t3.small` |
| `dag_name` | `load_raw_to_process_full_load_eks_dag` |
| `region` | `ap-southeast-1` |
| Stage full-load instance ARN | `arn:aws:dms:ap-southeast-1:<STAGE_ACCOUNT_ID>:rep:...` |
| Prod full-load instance ARN | `arn:aws:dms:ap-southeast-1:<PROD_ACCOUNT_ID>:rep:dms-prod-full-load` |

---

## SQL Reference (`sql_scripts/datalake_config.py`)

| Query constant | Purpose |
|---|---|
| `FETCH_RDS_ENDPOINT_QUERY` | Get schema credentials from `rds_endpoints` |
| `INSERT_QUERY` | INSERT into `transformation_master` (25 cols) |
| `INSERT_QUERY_WATERMARK` | INSERT into `watermark` table |
| `UPDATE_COLUMN_QUERY` | Update `tgt_schema_definition` only |
| `UPDATE_COLUMN_WITH_STATUS_QUERY` | Update `tgt_schema_definition` + set `status='ready'` |
| `SCHEMA_DEF_QUERY` | Get column names/types from `INFORMATION_SCHEMA` |

---

## Component-Specific Env Vars

| Variable | `new-table` | `new-column-*` | Notes |
|---|---|---|---|
| `SchemaName` | Required | Required | Source RDS schema |
| `TargetDbName` | Required | Required | Hudi target DB name |
| `TableNames` | Required | Required | Comma-separated table names |
| `ExecutionMethod` | Required | Required | `new-table` / `new-column-*` |
| `PartitionColumn` | Optional (blank) | **NOT used** | new-table only — Hudi partition column |
| `JobGroup` | Optional (`g6`) | **NOT used** | new-table only — existing tables keep the job group they were originally onboarded with |
| `Frequency` | Optional (`360`) | **NOT used** | new-table only — existing tables keep their original schedule |
| `IncrementalKey` | Optional (`updated_at`) | **NOT used** | new-table only — existing tables keep their original incremental key |
| `VAULT_STAGE_TOKEN` / `VAULT_PROD_TOKEN` | Required | Required | HashiCorp Vault token |
| `TEST_RUN` | Optional | Optional | Set to skip sleep + DAG trigger |

> **For `new-column-*`:** `JobGroup`, `Frequency`, `PartitionColumn`, and `IncrementalKey` are **not required and not used**. These values are not changed — the table already has its own job group, frequency, and incremental key from when it was first onboarded with `new-table`. Only the column schema (`tgt_schema_definition`) is updated. Do not ask for these parameters.

---

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| Table filtered out by validator | Table already in `transformation_master` | Use `new-column` execution method |
| DMS task fails to restart | Task in wrong state | Check DMS console; may need manual stop first |
| Instance resize times out | AWS capacity limits | Retry or use smaller instance class |
| `dag_variable_enum_validator` fails | Invalid `JobGroup` or `Frequency` | Check valid values in `datalake_config.dag_variable` |
| Wrong type in `schema_doc` | Unsupported MySQL type | Add mapping in `map_data_type()` |
| Vault 403 error | Expired token | Refresh `VAULT_STAGE_TOKEN` or `VAULT_PROD_TOKEN` |

---

## Tests

`tests/transactional_table_migration_automation/`
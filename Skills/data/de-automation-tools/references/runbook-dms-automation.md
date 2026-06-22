# DMS Automation

Automates AWS Database Migration Service (DMS) endpoint and replication task creation for migrating
RDS MySQL schemas to S3. Creates both a **full-load** task (initial bulk copy) and an **incremental**
task (CDC, ongoing changes).

**Entry point:** `src/dms_automation/main.py`

---

## Jenkins Job — DMSAutomation

### Parameters

| Parameter | Type | Notes |
|---|---|---|
| `Environment` | Choice | `stage` · `prod` |
| `SCHEMA_NAME` | String | Source RDS schema name |
| `SOURCE_ENGINE` | String | e.g., `mysql` |
| `SOURCE_DB_USER` | String | DB username (check `rds_endpoints` for existing users — see workflow below) |
| `SOURCE_DB_HOST` | String | RDS endpoint host |
| `SOURCE_DB_PORT` | String | e.g., `<port>` |
| `SOURCE_DB_VAULT_PATH` | String | HashiCorp Vault path for DB credentials (check existing pattern below) |
| `TARGET_FULL_LOAD_ENDPOINT` | String | DMS target endpoint for full-load task |
| `TARGET_INCR_LOAD_ENDPOINT` | String | DMS target endpoint for incremental/CDC task |
| `FULL_LOAD_INSTANCE` | String | Replication instance for full-load task |
| `INCR_LOAD_INSTANCE` | String | Replication instance for incremental task |

### Pre-check — ALWAYS Verify via Metabase Before Generating Config

> **This step is mandatory.** Do not ask the user for parameters or generate a Jenkins config
> until you have completed both queries below.

Use **Metabase MCP**, **DB ID 41** (`datalake_config`, MySQL).

#### Step 1 — Check if the schema already has an endpoint

```sql
SELECT schema_name, server_name, port, user_name, vault_key,
       full_load_task, incremental_task
FROM datalake_config.rds_endpoints
WHERE schema_name = '<schema_name_user_provided>';
```

**If a row is returned → STOP. Inform the user:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DMS ENDPOINT ALREADY EXISTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Schema       : {schema_name}
Source host  : {server_name}:{port}
DB user      : {user_name}
Vault path   : {vault_key}
Full-load task    : {full_load_task}
Incremental task  : {incremental_task}

No action needed — the DMS endpoint and replication tasks for this
schema are already configured. You do NOT need to run DMSAutomation.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If no row is returned → proceed to Step 2.**

---

#### Step 2 — Suggest user and vault path from existing entries

```sql
SELECT schema_name, server_name, user_name, vault_key
FROM datalake_config.rds_endpoints
ORDER BY schema_name;
```

Use the results to:
- **Confirm `SOURCE_DB_USER`** — the standard user across all entries is `<your-dms-db-user>`; flag if any schema uses a different user
- **Suggest `SOURCE_DB_VAULT_PATH`** — follow the existing pattern `datalake/dms/mysql/{hostname-prefix}` where `hostname-prefix` is the part of the host before the first `.` (e.g., host `mydb.<cluster-id>...` → `datalake/dms/mysql/mydb`)

Show the user a pre-fill suggestion before asking them to confirm:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRE-CHECK COMPLETE — Schema not yet registered
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Schema '{schema_name}' is NOT in rds_endpoints.
A new DMS endpoint needs to be created.

Based on existing entries, suggested values:
  SOURCE_DB_USER      : <your-dms-db-user>  (standard across all schemas)
  SOURCE_DB_VAULT_PATH: datalake/dms/mysql/{hostname-prefix}  (inferred from host)

Please provide or confirm:
  SOURCE_DB_HOST      : ?
  SOURCE_DB_PORT      : ?
  TARGET_FULL_LOAD_ENDPOINT  : ?
  TARGET_INCR_LOAD_ENDPOINT  : ?
  FULL_LOAD_INSTANCE  : ?
  INCR_LOAD_INSTANCE  : ?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Only after the user confirms all values → generate the Jenkins copy-paste block.

### Jenkins Copy-Paste Block

Once all values are confirmed, generate this block for the user:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — DMSAutomation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  <stage | prod>

SCHEMA_NAME:
  <schema_name>

SOURCE_ENGINE:
  mysql

SOURCE_DB_USER:
  <user_name>

SOURCE_DB_HOST:
  <rds_host>

SOURCE_DB_PORT:
  <port>

SOURCE_DB_VAULT_PATH:
  <vault_path>

TARGET_FULL_LOAD_ENDPOINT:
  <full_load_endpoint_id>

TARGET_INCR_LOAD_ENDPOINT:
  <incr_load_endpoint_id>

FULL_LOAD_INSTANCE:
  <full_load_instance_id>

INCR_LOAD_INSTANCE:
  <incr_load_instance_id>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Example** (from `example_db` schema):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — DMSAutomation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  prod

SCHEMA_NAME:
  example_db

SOURCE_ENGINE:
  mysql

SOURCE_DB_USER:
  <your-dms-db-user>

SOURCE_DB_HOST:
  mydb.<cluster-id>.<aws_region>.rds.amazonaws.com

SOURCE_DB_PORT:
  <port>

SOURCE_DB_VAULT_PATH:
  datalake/dms/mysql/mydb

TARGET_FULL_LOAD_ENDPOINT:
  tgt-full-load-s3-<datalake-bucket-prod>

TARGET_INCR_LOAD_ENDPOINT:
  tgt-incr-load-s3-<datalake-bucket-prod>

FULL_LOAD_INSTANCE:
  <full-load-instance>

INCR_LOAD_INSTANCE:
  <incr-load-instance>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## DMS Endpoints & Instances

### Stage

| Resource | ID |
|---|---|
| Full-load target endpoint | `tgt-full-load-s3-<datalake-bucket-stage>` |
| Incremental target endpoint | `tgt-incr-load-s3-<datalake-bucket-stage>` |
| Full-load replication instance | `<incr-load-instance>` |
| Incremental replication instance | `<incr-load-instance>` |

### Prod

| Resource | ID |
|---|---|
| Full-load target endpoint | `tgt-full-load-s3-<datalake-bucket-prod>` |
| Incremental target endpoint | `tgt-incr-load-s3-<datalake-bucket-prod>` |
| Full-load replication instance | `<full-load-instance>` |
| Incremental replication instance | `<incr-load-instance>` _(verify group number with user — multiple groups exist)_ |

> **Note:** Incremental replication instances have multiple groups (`group2`, `group3`, etc.). Ask the user which group to use if not specified, or check existing `rds_endpoints` entries for the same RDS host to see what group is already in use.

---

## File Structure

```
src/dms_automation/
  main.py                          # DMSManager class + orchestrator main()
  configs/
    dms_automation_configs.py      # Stage/prod DMS endpoint/instance IDs + DB hosts
  sql_scripts/
    dms_automation_sql.py          # RDS_ENDPOINT_CONNECTION query
  utils/
    db_connection.py               # MySQL context manager + query helpers
    vault_client.py                # HashiCorp Vault credential fetcher
```

---

## Key Class — `DMSManager`

Wraps boto3 DMS client with higher-level operations.

| Method | Description |
|---|---|
| `endpoint_exists(endpoint_id)` | Returns `True` if DMS endpoint already exists |
| `get_endpoint_arn(endpoint_id)` | Returns ARN string for the endpoint |
| `create_endpoint(config)` | Creates DMS endpoint; handles `ResourceAlreadyExistsFault` gracefully |
| `test_connection(endpoint_arn, replication_instance_arn)` | Polls connection test; 300s timeout |
| `get_replication_instance_arn(instance_id)` | Returns ARN for a named replication instance |
| `task_exists(task_id)` | Returns `True` if replication task exists |
| `create_selection_rule(schema_name)` | Builds table mapping JSON — include all tables in schema |
| `create_transformation_rule(schema_name)` | Adds `ar_h_change_seq` transformation column for CDC |
| `create_replication_task(task_config)` | Creates DMS task with both selection + transformation rules |
| `create_full_load_task(schema_name, ...)` | Creates full-load migration task |
| `create_incremental_task(schema_name, ...)` | Creates CDC task with `CdcStartTime` |
| `create_dms_tasks(...)` | Creates both full-load + incremental tasks |

**Table mapping rules:**
- **Selection rule:** Include all tables from `schema_name`
- **Transformation rule:** Adds `ar_h_change_seq` column to every table for CDC tracking

---

## Key Utility Functions

### `get_vault_credentials(vault_key, env)` (`vault_client.py`)

Fetches DB credentials from HashiCorp Vault.
- Retry: 5 attempts with exponential backoff (2s, 4s, 8s …)
- Token: `VAULT_STAGE_TOKEN` or `VAULT_PROD_TOKEN` env var

### `get_rds_endpoint_config(schema_name, rds_credentials)`

Queries `datalake_config.rds_endpoints` for the schema.
Returns: `(schema_name, server_name, port, user_name, vault_key)`

### `insert_rds_endpoint_config(endpoint_config, rds_credentials)`

INSERTs new schema into `datalake_config.rds_endpoints`.
Required fields: `schema_name`, `server_name`, `port`, `user_name`, `vault_key`
Also stores: `full_load_task: "full-load-{schema}"`, `incremental_task: "incr-load-{schema}"`

### `build_endpoint_config(schema_name, endpoint_config, vault_credentials)`

Constructs the DMS `CreateEndpoint` API payload.
Sets `MySQLSettings.ServerTimezone` for MySQL sources.
Returns: `{EndpointIdentifier, EndpointType, EngineName, ServerName, Port, DatabaseName, Username, Password}`

---

## Orchestration Flow (`main()`)

```
1. Validate env vars
2. Initialize DMSManager
3. Insert source endpoint config to rds_endpoints (if new)
4. Query rds_endpoints for config
5. Fetch DB password from Vault
6. Build DMS endpoint config dict
7. Create or confirm endpoint exists
8. Test endpoint connection (300s timeout)
9. create_dms_tasks() → full-load + incremental tasks
```

---

## SQL Reference (`dms_automation_sql.py`)

```sql
-- RDS_ENDPOINT_CONNECTION
SELECT schema_name, server_name, port, user_name, vault_key
FROM datalake_config.rds_endpoints
WHERE schema_name = %s
```

---

## Error Handling

| Error | Source | Behavior |
|---|---|---|
| `ResourceAlreadyExistsFault` | `create_endpoint()` | Logs warning, continues (idempotent) |
| `DbConnectionError` | DB connection | Raised, stops execution |
| Connection test timeout (300s) | `test_connection()` | Raises exception |
| `ClientError` | boto3 DMS | Caught, prints error |
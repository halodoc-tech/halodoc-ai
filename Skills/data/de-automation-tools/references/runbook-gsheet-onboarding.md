# GSheet Onboarding Automation

Automates the process of onboarding a Google Sheet into the data lake. Registers the sheet in
`datalake_config.gsheet_export`, updates the Glue crawler with the new S3 target, and triggers
the Airflow DAG to ingest the data.

**Entry point:** `src/gsheet_onbording_automation/main.py`

> **Note:** Directory is `gsheet_onbording_automation` — single 'a' in "onbording" is intentional
> (matches codebase). Do not rename.

---

## Jenkins Job — GsheetIngestionAutomation

### Parameters

| Parameter | Type | Options / Notes |
|---|---|---|
| `Environment` | Choice | `stage` · `prod` |
| `ExecutionMethod` | Choice | `new-table` · `new-column` |
| `GSHEET_ID` | String | Google Sheet document ID (from the sheet URL) |
| `SHEET_RANGE` | String | e.g., `Sheet1!A1:Z` or `example_sheet!A1:C` |
| `GSHEET_TABLE_NAME` | String | Target table name in the datalake |
| `JOB_GROUP` | String | `g0` or `g1` |
| `BUSINESS_UNIT` | String | Business unit tag (see note below) |

> **BUSINESS_UNIT — how to find valid values:** Before asking the user, query Metabase DB 41 to show them the options already in use:
>
> ```sql
> SELECT DISTINCT business_unit
> FROM datalake_config.gsheet_export
> ORDER BY business_unit;
> ```
>
> Known existing values include: `business_unit_a`, `business_unit_b`. Show the list to the user and ask them to pick one or confirm a new one.

### Pre-check — ALWAYS Verify via Metabase Before Generating Config

> **This step is mandatory.** Run the queries below before asking for any missing parameters
> or generating a Jenkins config. The execution method determines which checks to run.

Use **Metabase MCP**, **DB ID 41** (`datalake_config`, MySQL).

---

#### For `new-table` — Two checks required

**Check 1: Sheet ID must NOT already be registered**

```sql
SELECT sheet_id, sheetname, sheet_range, business_unit, job_group, active_flag
FROM datalake_config.gsheet_export
WHERE sheet_id = '<provided_sheet_id>';
```

If a row is returned → **STOP. Tell the user:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SHEET ALREADY REGISTERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This Sheet ID is already in the datalake:
  Table name  : {sheetname}
  Sheet range : {sheet_range}
  Business unit: {business_unit}
  Job group   : {job_group}
  Active      : {active_flag}

No action needed for new-table.
If you want to update the sheet range, use ExecutionMethod = new-column instead.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Check 2: Table name must NOT already be in use**

```sql
SELECT sheet_id, sheetname, sheet_range
FROM datalake_config.gsheet_export
WHERE sheetname = '<provided_table_name>';
```

If a row is returned → **Warn the user:**

```
The table name '{table_name}' is already registered with a different Sheet ID ({sheet_id}).
Please use a different table name, or confirm this is the same sheet you want to update.
```

If both checks pass → proceed to generate the Jenkins config.

---

#### For `new-column` — Sheet ID must already exist

```sql
SELECT sheet_id, sheetname, sheet_range, business_unit, job_group, active_flag
FROM datalake_config.gsheet_export
WHERE sheet_id = '<provided_sheet_id>';
```

**If no row is returned → STOP. Tell the user:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SHEET NOT FOUND
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The Sheet ID '{sheet_id}' was not found in the datalake records.

To fix this, double-check the Sheet ID:
  1. Open the Google Sheet
  2. Look at the URL: docs.google.com/spreadsheets/d/{SHEET_ID}/edit
  3. Copy the ID between /d/ and /edit

If you meant to onboard a brand new sheet, use ExecutionMethod = new-table instead.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If a row is returned → show current state and confirm the update:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SHEET FOUND — Confirm Update
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Sheet ID    : {sheet_id}
Table name  : {sheetname}
Current range: {sheet_range}
New range   : {new_sheet_range_provided_by_user}

The sheet range will be updated from '{sheet_range}' to '{new_sheet_range}'.
Confirm to proceed.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> **Note:** For `new-column`, only `SHEET_RANGE` is updated in `gsheet_export`. The other
> fields (`GSHEET_TABLE_NAME`, `JOB_GROUP`, `BUSINESS_UNIT`) are not needed — do not ask for them.

---

### Additional Validations (apply to both methods)

Run these checks and flag any issues **before** generating config. Each message tells the user exactly what to fix:

| Check | Condition | What to tell the user |
|---|---|---|
| Sheet ID format | Should be ~44 chars, alphanumeric + hyphens/underscores | "The Sheet ID looks too short/long. Copy it directly from the Google Sheet URL: the part between `/d/` and `/edit`." |
| Sheet range format | Must follow `SheetName!StartCell:EndCol` pattern | "The range `{value}` doesn't look right. Use the format `SheetName!A1:Z` (e.g., `Sheet1!A1:Z` or `example_sheet!A1:C`)." |
| Job group | Must be `g0` or `g1` | "Job group must be `g0` or `g1`. You entered `{value}`." |
| Table name (new-table) | Should not contain spaces or special characters | "Table names can only contain letters, numbers, and underscores. `{value}` contains invalid characters." |

---

### Jenkins Copy-Paste Block

**For `new-table`:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — GsheetIngestionAutomation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  <stage | prod>

ExecutionMethod:
  new-table

GSHEET_ID:
  <sheet_id>

SHEET_RANGE:
  <SheetName!A1:Z>

GSHEET_TABLE_NAME:
  <table_name>

JOB_GROUP:
  <g0 | g1>

BUSINESS_UNIT:
  <business_unit>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**For `new-column`** (only SHEET_RANGE needed — other fields come from existing record):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — GsheetIngestionAutomation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  <stage | prod>

ExecutionMethod:
  new-column

GSHEET_ID:
  <sheet_id>

SHEET_RANGE:
  <updated_range>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Example** (from `example_sheet` sheet):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JENKINS PARAMETERS — GsheetIngestionAutomation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  prod

ExecutionMethod:
  new-table

GSHEET_ID:
  <your-google-sheet-id>

SHEET_RANGE:
  example_sheet!A1:C

GSHEET_TABLE_NAME:
  example_sheet

JOB_GROUP:
  g0

BUSINESS_UNIT:
  business_unit_a

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Execution Methods

Controlled by `ExecutionMethod` Jenkins parameter:

| Method | What it does |
|---|---|
| `new-table` | INSERTs new row to `gsheet_export` → updates Glue crawler S3 targets → **runs** crawler → triggers DAG |
| `new-column` | Updates `sheet_range` for existing sheet in `gsheet_export` → triggers DAG only (no crawler update) |

---

## File Structure

```
src/gsheet_onbording_automation/
  main.py                      # Orchestrator
  configs/
    datalake_config_creds.py   # Stage/prod DB host/user
  sql_scripts/
    gsheet_export.py           # INSERT and UPDATE SQL templates
  utils/
    api.py                     # trigger_dag(), get_session_info()
    variables.py               # Crawler names, DAG name, MWAA env names
```

---

## Key Functions (`main.py`)

| Function | Description |
|---|---|
| `gsheet_validator(cursor, sheet_range, sheet_id)` | Checks if sheet already exists in `gsheet_export`; returns existing row or `None` |
| `handle_new_table(...)` | Validates no duplicate → INSERTs new row |
| `handle_new_column(cursor, sheet_id, sheet_range)` | Updates `sheet_range` for existing sheet matching `sheet_id` |
| `insert_to_gsheet_export(...)` | Routes to `handle_new_table` or `handle_new_column` |
| `get_crawler_data_sources(glue, crawler_name)` | Returns current `S3Targets` list from Glue crawler |
| `update_crawler(glue, new_s3_targets, crawler_name)` | Appends new S3 path to crawler targets (does not replace existing) |
| `run_crawler(glue, crawler_name)` | Starts the Glue crawler — only called for `new-table` |

**`gsheet_export` INSERT columns:**
`source · sheetname · sheet_id · sheet_range · target_s3_bucket · target_s3_prefix · business_unit · active_flag · job_group`

---

## Key Functions (`utils/api.py`)

### `get_session_info(region, env_name)`
Authenticates to MWAA and returns `(hostname, jwt_token)`.

### `trigger_dag(env, dag_id, region, sheet_range)`
Triggers `gsheet_migration_by_sheet_range_dag` via MWAA REST API.
- POST to `/api/v2/dags/{dag_id}/dagRuns`
- Payload: `{logical_date, conf: {sheet_range}}`
- Polls DAG status for up to 300s timeout

---

## Orchestration Flow

```
1. Read all env vars
2. Validate required fields based on execution_method
3. Get DB connection
4. insert_to_gsheet_export() → INSERT or UPDATE gsheet_export
5. trigger_dag() → Trigger gsheet_migration_by_sheet_range_dag
6. Get Glue client (boto3)
7. update_crawler() → Add new S3 path to crawler targets
8. If new-table: run_crawler() → Start crawler execution
```

---

## Configuration (`variables.py`)

| Variable | Value |
|---|---|
| `stage_crawler_name` | `sheet_crawler` |
| `prod_crawler_name` | `datalake_raw_gsheet_crawler` |
| `dag_name` | `gsheet_migration_by_sheet_range_dag` |
| `stage_airflow_env_name` | `<stage-airflow-env-name>` |
| `prod_airflow_env_name` | `<prod-airflow-env-name>` |

---

## SQL Reference (`sql_scripts/gsheet_export.py`)

```sql
-- INSERT_INTO_GSHEET_EXPORT
INSERT INTO datalake_config.gsheet_export
  (source, sheetname, sheet_id, sheet_range,
   target_s3_bucket, target_s3_prefix,
   business_unit, active_flag, job_group)
VALUES (...)

-- UPDATE_GSHEET_EXPORT
UPDATE datalake_config.gsheet_export
  SET sheet_range = %s
WHERE sheet_id = %s
```

---

## Common Issues

| Symptom | Cause | Clear fix |
|---|---|---|
| Sheet not found for `new-column` | Wrong Sheet ID | Copy Sheet ID directly from URL: `/spreadsheets/d/{THIS_PART}/edit` |
| Duplicate sheet error on `new-table` | Sheet ID already in `gsheet_export` | Use `new-column` to update an existing sheet |
| Table name conflict on `new-table` | `sheetname` already registered | Choose a different table name |
| DAG trigger timeout (300s) | DAG stuck | Check MWAA console for the DAG run status |
| Crawler not updated | Wrong crawler name for env | Verify `stage_crawler_name` vs `prod_crawler_name` in `variables.py` |
| JWT auth fails | Stale AWS session token | Refresh `AWS_SESSION_TOKEN` |

---

## Tests

`tests/gsheet_onbording_automation/`
- `test_main.py` — Sheet validation, DB insert/update operations
- `test_api.py` — DAG trigger API calls, session info retrieval
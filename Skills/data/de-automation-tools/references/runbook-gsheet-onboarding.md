# GSheet → Redshift Loader

Loads a Google Sheet **directly into a Redshift table** with an idempotent
**delete-insert upsert** on a business key. No S3, Glue, DMS, or Airflow — just
the sheet and Redshift.

**Entry point:** `src/gsheet_onbording_automation/main.py`

---

## What it does

For each target declared in `config.yml`:

1. Read the sheet range via the Google Sheets API (service-account auth).
2. `CREATE SCHEMA IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS` (columns from the
   declared `columns` spec, or inferred from the sheet header as `VARCHAR`).
3. Upsert via a staging temp table:
   ```sql
   CREATE TEMP TABLE stg (LIKE schema.table);
   INSERT INTO stg ... ;                          -- the sheet rows
   DELETE FROM schema.table USING stg
     WHERE schema.table.<bk> = stg.<bk> ...;       -- composite key supported
   INSERT INTO schema.table SELECT * FROM stg;
   ```
   Re-running replaces exactly the rows whose business key is in the sheet.

---

## Configure (`config.yml`)

```yaml
redshift:
  host: <redshift-host>
  port: 5439
  db_name: <redshift-db>
  user: <redshift-user>

gsheet:
  service_account_json: <path-to-google-service-account-json>
  targets:
    - sheet_id:      <your-google-sheet-id>
      sheet_range:   Sheet1!A1:Z
      target_schema: public
      target_table:  sales_from_sheet
      business_key:  [order_id]      # one or more columns
      columns:                        # optional; omit to infer all as VARCHAR
        order_id:   BIGINT
        amount:     "DECIMAL(18,2)"
        updated_at: TIMESTAMP
```

- **`business_key`** — the merge key. Existing rows with a matching key are
  deleted before insert. Use a list for composite keys.
- **`columns`** — declared types pin the DDL and restrict/order which sheet
  columns are loaded. Omit to load every header column as `VARCHAR(65535)`.

---

## Secrets (env vars — never in config)

| Env var | Purpose |
|---|---|
| `REDSHIFT_PASSWORD` | Redshift password |
| `GOOGLE_APPLICATION_CREDENTIALS` | path to the Google service-account JSON (overrides `gsheet.service_account_json`) |

The service account must have **read** access to the sheet (share the sheet with
its client email).

---

## Run

```bash
cd src/gsheet_onbording_automation
pip install -r requirements.txt
python main.py                       # all targets
TARGET_TABLE=sales_from_sheet python main.py   # one target
```

---

## Notes

- Idempotent — safe to re-run / schedule (cron, Airflow, any scheduler).
- `backend.mode: yaml` records each load in `registry/gsheet_targets.yml`
  (target, sheet, business key, row count) for tracking.
- Redshift is reached with `psycopg2` (Postgres wire protocol).

"""
Google Sheet -> Redshift loader.

Reads a Google Sheet and loads it into a Redshift table with a delete-insert
upsert on a business key (idempotent: rerunning replaces the matching rows).
Targets are declared in config.yml under `gsheet.targets`.

  Run all targets:        python main.py
  Run one target:         TARGET_TABLE=<schema.table | table> python main.py

Secrets / auth (env vars — never in config):
  REDSHIFT_PASSWORD               Redshift password
  GOOGLE_APPLICATION_CREDENTIALS  path to a Google service-account JSON
                                  (or set gsheet.service_account_json in config.yml)
"""
import os
import pathlib
import sys

import gspread
import psycopg2
from psycopg2.extras import execute_values
import yaml

import registry


def _config():
    path = os.environ.get("DE_CONFIG_PATH")
    if not path:
        for parent in pathlib.Path(__file__).resolve().parents:
            if (parent / "config.yml").exists():
                path = parent / "config.yml"
                break
    with open(path) as handle:
        return yaml.safe_load(handle) or {}


def read_sheet(sheet_id, sheet_range, sa_json):
    """Return (header, rows) from a Google Sheet. sheet_range like 'Sheet1!A1:Z'."""
    client = gspread.service_account(filename=sa_json)
    spreadsheet = client.open_by_key(sheet_id)
    if "!" in sheet_range:
        ws_name, cell_range = sheet_range.split("!", 1)
        values = spreadsheet.worksheet(ws_name).get(cell_range)
    else:
        values = spreadsheet.sheet1.get_all_values()
    if not values:
        return [], []
    return [c.strip() for c in values[0]], values[1:]


def ensure_table(cur, schema, table, columns, col_types):
    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}";')
    cols_ddl = ", ".join(f'"{c}" {col_types.get(c, "VARCHAR(65535)")}' for c in columns)
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{schema}"."{table}" ({cols_ddl});')


def upsert(conn, schema, table, columns, business_key, rows):
    """Delete-insert merge via a staging temp table (supports composite keys)."""
    full = f'"{schema}"."{table}"'
    col_list = ", ".join(f'"{c}"' for c in columns)
    cur = conn.cursor()
    cur.execute(f"CREATE TEMP TABLE stg (LIKE {full});")
    execute_values(
        cur,
        f"INSERT INTO stg ({col_list}) VALUES %s",
        [tuple(r[i] if i < len(r) else None for i in range(len(columns))) for r in rows],
    )
    join_cond = " AND ".join(f'{full}."{k}" = stg."{k}"' for k in business_key)
    cur.execute(f"DELETE FROM {full} USING stg WHERE {join_cond};")
    cur.execute(f"INSERT INTO {full} ({col_list}) SELECT {col_list} FROM stg;")
    cur.execute("DROP TABLE stg;")
    conn.commit()
    cur.close()


def run_target(rs_cfg, sa_json, target):
    schema = target["target_schema"]
    table = target["target_table"]
    business_key = target["business_key"]
    if isinstance(business_key, str):
        business_key = [business_key]
    col_types = target.get("columns") or {}

    header, rows = read_sheet(target["sheet_id"], target["sheet_range"], sa_json)
    if not header:
        print(f"[{schema}.{table}] sheet is empty — skipping")
        return

    if col_types:
        # declared schema wins: select + order columns by the declared spec
        columns = list(col_types.keys())
        pos = {h: i for i, h in enumerate(header)}
        missing = [c for c in columns if c not in pos]
        if missing:
            sys.exit(f"[{schema}.{table}] declared columns missing from sheet header: {missing}")
        rows = [[r[pos[c]] if pos[c] < len(r) else None for c in columns] for r in rows]
    else:
        # infer columns from the sheet header; all VARCHAR
        columns = header

    for key in business_key:
        if key not in columns:
            sys.exit(f"[{schema}.{table}] business_key '{key}' not in columns {columns}")

    conn = psycopg2.connect(
        host=rs_cfg["host"], port=rs_cfg.get("port", 5439),
        dbname=rs_cfg["db_name"], user=rs_cfg["user"],
        password=os.environ["REDSHIFT_PASSWORD"],
    )
    try:
        cur = conn.cursor()
        ensure_table(cur, schema, table, columns, col_types)
        conn.commit()
        cur.close()
        upsert(conn, schema, table, columns, business_key, rows)
        print(f"[{schema}.{table}] upserted {len(rows)} rows (delete-insert on {business_key})")
    finally:
        conn.close()

    if registry.backend_mode() == "yaml":
        record = {
            "target_schema": schema, "target_table": table,
            "sheet_id": target["sheet_id"], "sheet_range": target["sheet_range"],
            "business_key": business_key, "last_rows": len(rows),
        }
        if not registry.update("gsheet_targets",
                               {"target_schema": schema, "target_table": table}, record):
            registry.insert("gsheet_targets", record)


def main():
    cfg = _config()
    gsheet_cfg = cfg.get("gsheet") or {}
    rs_cfg = cfg.get("redshift") or {}
    sa_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or gsheet_cfg.get("service_account_json")
    if not sa_json:
        sys.exit("Set GOOGLE_APPLICATION_CREDENTIALS env var or gsheet.service_account_json in config.yml")

    targets = gsheet_cfg.get("targets") or []
    if not targets:
        sys.exit("No gsheet.targets defined in config.yml")

    only = os.environ.get("TARGET_TABLE")
    if only:
        wanted = only.split(".")[-1]
        targets = [t for t in targets if t["target_table"] == wanted]
        if not targets:
            sys.exit(f"No target matching TARGET_TABLE={only}")

    for target in targets:
        run_target(rs_cfg, sa_json, target)


if __name__ == "__main__":
    main()

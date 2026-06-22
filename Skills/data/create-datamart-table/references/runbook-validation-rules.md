# Runbook: Validation Rules

Source of truth extracted from `src/datamart_module/validator.py` and `src/datamart_table_creation/steps/validation_steps.py`.

---

## Validation Checklist (run before generating final output)

### 1. table_name
- [ ] Length: 3–127 characters
- [ ] Lowercase only (automation auto-lowercases, but confirm intent)
- [ ] No spaces (use underscores)
- [ ] Must NOT already exist in `datalake_config.dimensional_model`

**Check via Metabase MCP:**
```
Use Redshift DB:
SELECT COUNT(*) FROM datalake_config.dimensional_model
WHERE tgt_table_name = '<table_name>'
  AND active_flag = 'Y'
```
→ Must return 0

---

### 2. table_type
Must be one of:
- `presentations`
- `monetization`
- `dim_fact`
- `dim_fact_new_dag`
- `monetization_dwh`
- `report_layer`
- `nrt_table`

---

### 3. redshift_ddl
- Must be valid JSON
- Must have `schema`, `distkey`, `sortkey` keys
- Column types must be valid Redshift types
- VARCHAR lengths must be realistic (warn if less than 50 for name fields)

---

### 4. rds_config — required keys
See `runbook-table-types.md` for exact required keys per table_type.

**No extra keys allowed** — the validator rejects any key not in the required set.

---

### 5. schedule (cron expression)
- Must be valid 5-part cron: `minute hour day month weekday`
- Example: `0 1 * * *` = every day at 01:00 UTC (08:00 WIB)
- Validate: does it match expected 5-part pattern?
- **Important:** schedule is in UTC, not WIB. WIB = UTC+7.
  - WIB 00:00 → UTC `0 17 * * *` (previous day)
  - WIB 07:00 → UTC `0 0 * * *`
  - WIB 08:00 → UTC `0 1 * * *`
  - WIB 12:00 → UTC `0 5 * * *`

**Reference:** Check existing schedules using Metabase:
https://<metabase-internal-host>/question/<card-id>-table-monitor

---

### 6. table_dependencies
- Must be a string containing a Python-style list of dicts
- Each dict must have `table_name` key
- `table_name` must be in `schema.table` format (dot-separated)
- Forbidden schemas: `reference_table`, `adhoc_data`
- Table must not be empty after the dot

**Valid format:**
```
"[{'table_name': 'dwh.fact_orders', 'is_skip_allowed': 'False'}]"
```

**Invalid formats (reject these):**
```
"dwh.fact_orders, dwh.dim_product"  ← comma-separated string, not a list
"[test.syntax, test.invalid"                ← not parseable
"[]"                                         ← empty list not allowed
```

**Check dependencies exist via Metabase MCP:**
```
Use Redshift DB:
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = '<schema>' AND table_name = '<table>'
```

---

### 7. business_unit (dim_fact and dim_fact_new_dag only)

**For `dim_fact`** — must already exist:
```
Use Redshift DB:
SELECT DISTINCT business_unit FROM datalake_config.dimensional_model
WHERE table_type = '<facts|dimensions>'
  AND active_flag = 'Y'
```
→ User's value must be in this list

**For `dim_fact_new_dag`** — must NOT already exist:
→ User's value must NOT be in the list above (creating a new business unit)

---

### 8. dependency_type (presentations and monetization only)
Must be exactly `strong` or `weak` — nothing else.

---

### 9. table_type in rds_config (dim_fact types only)
Must be exactly `facts` or `dimensions` — nothing else.

---

## Common Errors and Fixes

| Error | Cause | Fix |
|---|---|---|
| `Key 'schedule' is required` | Missing schedule for a table type that needs it | Add schedule cron |
| `Key 'X' is not required` | Extra key in rds_config | Remove the unexpected key |
| `dependency_type must be strong or weak` | Typo in dependency_type | Fix to `strong` or `weak` |
| `business unit is not exist` | business_unit value not in DB | Check valid values via Metabase |
| `table_dependencies must be a list` | Wrong format for dependencies | Wrap in `[{...}]` |
| `table_name must be in schema.table format` | Missing schema prefix | Add schema: `dwh.table_name` |
| `Table already exists in datawarehouse` | table_name already in dimensional_model | Choose a different name |
| `DDL cannot be executed` | Invalid Redshift DDL | Check column types |

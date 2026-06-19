# Airflow Monitoring

Monitors MWAA (Managed Workflows for Apache Airflow) health and DAG import errors, then raises
alerts (stdout + CSV, and an optional webhook) if issues persist after a 60-second re-check.
Health snapshots are written to a CSV — no database required.

**Entry point:** `src/airflow_monitoring/health_checker.py`

---

## File Structure

```
src/airflow_monitoring/
  health_checker.py         # Main logic + entry point
  utils/
    alert_notification.py  # send_alert() — stdout + CSV + optional webhook
    variables.py           # MWAA env names, region, component names
```

---

## Key Functions

### `create_web_token()`
Creates an AWS MWAA web login token via boto3.
- Reads env vars: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `Environment`
- Validates `Environment` against `stage_airflow_env_name` / `prod_airflow_env_name`
- Raises on invalid environment or non-200 HTTP response
- Returns boto3 response with `WebServerHostname` and `WebToken`

### `get_session_info()`
Returns `(web_server_hostname, jwt_token)` for MWAA REST API calls.
Flow: `create_web_token()` → POST login to `https://{hostname}/aws_mwaa/login` → extract `_token` cookie

### `checkInstanceHealth()`
Polls `GET /api/v2/monitor/health`.
Checks 4 components: `Metadatabase`, `Scheduler`, `Triggerer`, `Dagprocessor`.
Returns list of unhealthy component names.

### `checkImportErrors()`
Polls `GET /api/v2/importErrors` and filters to errors in the last 1 hour.
Returns: `(error_count, [dag_names])`

### `main()` — Double-check retry logic

```
1. checkInstanceHealth()
   └─ If unhealthy → wait 60s → check again
      └─ Still unhealthy → send_alert()

2. checkImportErrors()
   └─ If errors → wait 60s → check again
      └─ Still errors → send_gchat_alert()
```

Alerts fire **only** when the issue persists after the 60s re-check — avoids false positives.

---

## Alerting (`send_alert(message)` in `alert_notification.py`)

Generic, no provider credentials hard-coded:
- Always prints the alert and appends it to `airflow_alerts.csv`
- If `ALERT_WEBHOOK_URL` is set, also POSTs `{"text": message}` — works with both
  Slack and Google Chat incoming webhooks
- Health snapshots are written to `airflow_health.csv` each run (`write_health_snapshot`)

---

## Configuration (`variables.py`)

```python
stage_airflow_env_name = '<stage-airflow-env-name>'
prod_airflow_env_name  = '<prod-airflow-env-name>'
components = {'Metadatabase', 'Scheduler', 'Triggerer', 'Dagprocessor'}
```

---

## Component-Specific Env Vars

| Variable | Required | Description |
|---|---|---|
| `ALERT_WEBHOOK_URL` | Optional | Incoming webhook to POST alerts to (Slack/Google Chat); omit for stdout + CSV only |
| `ALERT_CSV_PATH` / `HEALTH_CSV_PATH` | Optional | Override the alert / health-snapshot CSV paths |

(Standard common env vars — `Environment`, `AWS_ACCESS_KEY_ID`, etc. — also required.)

---

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid environment` error | `Environment` env var missing or wrong | Set to `stage` or `prod` |
| JWT token missing | Login POST failed | Check AWS credentials are valid |
| Health check always unhealthy | MWAA instance down | Check AWS Console for MWAA status |
| Import errors not caught | Error timestamp > 1 hour old | By design — only recent errors trigger alert |
| Webhook alert not sent | `ALERT_WEBHOOK_URL` unset | Set it, or check stdout / `airflow_alerts.csv` |

---

## Tests

`tests/airflow_monitoring/test_health_checker.py`
- Web token creation (success, invalid env, HTTP errors)
- Session info retrieval (success, exceptions, login failures)
- Instance health checks (all healthy, partial failures)
- Import error detection (new errors, old errors skipped)
- Main orchestration: alert triggered only when double-check still fails
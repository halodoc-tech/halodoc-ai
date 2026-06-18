# Airflow Monitoring

Monitors MWAA (Managed Workflows for Apache Airflow) health and DAG import errors, then fires
alerts via Google Chat and Slack if issues persist after a 60-second re-check.

**Entry point:** `src/airflow_monitoring/health_checker.py`

---

## File Structure

```
src/airflow_monitoring/
  health_checker.py         # Main logic + entry point
  utils/
    alert_notification.py  # send_gchat_alert(), send_slack_alert()
    variables.py           # MWAA env names, component names
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
      └─ Still unhealthy → send_gchat_alert()

2. checkImportErrors()
   └─ If errors → wait 60s → check again
      └─ Still errors → send_gchat_alert()
```

Alerts fire **only** when the issue persists after the 60s re-check — avoids false positives.

---

## Alert Channels

**Google Chat** (`send_gchat_alert(message)` in `alert_notification.py`):
- Hardcoded webhook URL
- POST with `{"text": message}`

**Slack** (`send_slack_alert(message)` in `alert_notification.py`):
- Uses `slack_sdk` WebClient
- Channel: `C02BM4FDJTG` (`datalake-prod-alerts`)
- Token from `SLACK_BOT_TOKEN` env var

---

## Configuration (`variables.py`)

```python
stage_airflow_env_name = 'halodoc-stage-airflow-de-306'
prod_airflow_env_name  = 'halodoc-datalake-prod-airflow-mwaa-3'
components = {'Metadatabase', 'Scheduler', 'Triggerer', 'Dagprocessor'}
```

---

## Component-Specific Env Vars

| Variable | Required | Description |
|---|---|---|
| `SLACK_BOT_TOKEN` | For Slack alerts | Slack SDK bot token |

(Standard common env vars — `Environment`, `AWS_ACCESS_KEY_ID`, etc. — also required.)

---

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid environment` error | `Environment` env var missing or wrong | Set to `stage` or `prod` |
| JWT token missing | Login POST failed | Check AWS credentials are valid |
| Health check always unhealthy | MWAA instance down | Check AWS Console for MWAA status |
| Import errors not caught | Error timestamp > 1 hour old | By design — only recent errors trigger alert |
| Slack alert not sent | `SLACK_BOT_TOKEN` missing | Set the env var |

---

## Tests

`tests/airflow_monitoring/test_health_checker.py`
- Web token creation (success, invalid env, HTTP errors)
- Session info retrieval (success, exceptions, login failures)
- Instance health checks (all healthy, partial failures)
- Import error detection (new errors, old errors skipped)
- Main orchestration: alert triggered only when double-check still fails
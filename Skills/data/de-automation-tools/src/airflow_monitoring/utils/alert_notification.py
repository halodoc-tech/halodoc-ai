"""
Generic alert sink — no provider credentials are hard-coded.

`send_alert(message)` always prints the alert and appends it to a CSV log, and —
if `ALERT_WEBHOOK_URL` is set — POSTs `{"text": message}` to that URL. A plain
`{"text": ...}` body works with both Slack and Google Chat incoming webhooks, so
the same code targets either by just setting the env var.

Env vars:
  ALERT_WEBHOOK_URL  optional — incoming-webhook URL to POST alerts to
  ALERT_CSV_PATH     optional — CSV log path (default: airflow_alerts.csv)
"""
import csv
import os
from datetime import datetime, timezone

import requests

ALERT_CSV = os.environ.get("ALERT_CSV_PATH", "airflow_alerts.csv")


def _record_csv(message):
    is_new = not os.path.exists(ALERT_CSV)
    with open(ALERT_CSV, "a", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(["timestamp_utc", "message"])
        writer.writerow([datetime.now(timezone.utc).isoformat(), message])


def send_alert(message):
    print(f"[ALERT] {message}")
    _record_csv(message)
    webhook = os.environ.get("ALERT_WEBHOOK_URL")
    if webhook:
        try:
            requests.post(webhook, json={"text": message}, timeout=10)
        except Exception as exc:
            print(f"Failed to post alert to webhook: {exc}")

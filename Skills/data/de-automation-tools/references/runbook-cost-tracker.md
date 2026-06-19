# Cost Tracker

Reports AWS **Cost Explorer spend per service for the previous full week**
(Sunday–Saturday) and writes it to a CSV. Optionally filtered by a CostCenter tag.

**Entry point:** `src/cost_tracker_automation/main.py`

---

## What it does

1. Computes the previous full week (Sun–Saturday) in the configured timezone.
2. Calls AWS Cost Explorer `get_cost_and_usage` grouped by `SERVICE`
   (AmortizedCost), optionally filtered by a CostCenter tag.
3. Prints a per-service breakdown + total, and writes a CSV
   (`week_start, week_end, service, amortized_cost`).

No database, no Redshift, no CloudWatch — just Cost Explorer → CSV. This is a
deliberately simple, generic version; extend `cost_by_service()` if you need
more (S3/CloudWatch/warehouse metrics, a database sink, etc.).

---

## Configure (`config.yml`)

```yaml
aws:
  region: <aws_region>

cost_tracker:
  timezone: UTC                  # week window is computed in this tz
  cost_center_tag_key: ""        # optional Cost Explorer tag filter; blank = no filter
  cost_center_tag_values: []     # e.g. ["DE", "DE-DS"]
  csv_path: ""                   # optional; blank = cost_by_service_<start>_to_<end>.csv
```

## Secrets (env)

AWS auth uses the standard boto3 chain — env vars, shared profile, or instance
role. Needs `ce:GetCostAndUsage`. Override the output path with `COST_CSV_PATH`.

## Run

```bash
cd src/cost_tracker_automation
pip install -r requirements.txt
python main.py
```

Example output:

```
AWS cost by service — 2025-04-06 to 2025-04-12 (<aws_region>)
--------------------------------------------------
Amazon Redshift                             633.08
Amazon Simple Storage Service               333.91
...
TOTAL                                      2067.85

Wrote 30 rows to cost_by_service_2025-04-06_to_2025-04-12.csv
```

## Notes

- Idempotent and read-only against AWS — safe to run/schedule anywhere
  (cron, Airflow, CI). No parameters required.
- Cost Explorer end dates are exclusive — the code adds one day internally.

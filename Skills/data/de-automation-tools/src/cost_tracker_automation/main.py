"""
Weekly AWS cost-by-service report (generic).

Pulls AWS Cost Explorer AmortizedCost for the previous full week
(Sunday–Saturday), grouped by service, and prints a per-service breakdown plus a
total. Optionally filters by a CostCenter tag.

Config comes from the skill's config.yml (aws.region + an optional cost_tracker
block). AWS auth uses the standard boto3 credential chain (env vars / shared
profile / instance role) — no custom credential handling.

    cd cost_tracker_automation && python main.py
"""
import csv
import os
import pathlib
from datetime import datetime, timezone, timedelta

import boto3
import pytz
import yaml


def _config():
    path = os.environ.get("DE_CONFIG_PATH")
    if not path:
        for parent in pathlib.Path(__file__).resolve().parents:
            if (parent / "config.yml").exists():
                path = parent / "config.yml"
                break
    with open(path) as handle:
        return yaml.safe_load(handle) or {}


def previous_week(tz_name="UTC"):
    """Return (start, end) as YYYY-MM-DD for the previous full Sunday–Saturday week."""
    tz = pytz.timezone(tz_name)
    now = datetime.now(timezone.utc).astimezone(tz)
    days_to_sunday = now.weekday() + 1  # Mon=0 … Sun=6 → step back to last Sunday
    sunday_last = now - timedelta(days=days_to_sunday) - timedelta(weeks=1)
    saturday_last = sunday_last + timedelta(days=6)
    return sunday_last.strftime("%Y-%m-%d"), saturday_last.strftime("%Y-%m-%d")


def cost_by_service(start, end, region, tag_key=None, tag_values=None):
    """Cost Explorer AmortizedCost grouped by SERVICE, summed over the window."""
    client = boto3.client("ce", region_name=region)
    # Cost Explorer treats the end date as exclusive — add one day.
    end_exclusive = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    kwargs = dict(
        TimePeriod={"Start": start, "End": end_exclusive},
        Granularity="DAILY",
        Metrics=["AmortizedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    if tag_key and tag_values:
        kwargs["Filter"] = {"Tags": {"Key": tag_key, "Values": tag_values, "MatchOptions": ["EQUALS"]}}

    response = client.get_cost_and_usage(**kwargs)
    totals = {}
    for day in response["ResultsByTime"]:
        for group in day["Groups"]:
            service = group["Keys"][0]
            amount = round(float(group["Metrics"]["AmortizedCost"]["Amount"]), 2)
            totals[service] = round(totals.get(service, 0.0) + amount, 2)
    return totals


def write_csv(path, start, end, totals):
    """Write per-service costs to a CSV: week_start, week_end, service, amortized_cost."""
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["week_start", "week_end", "service", "amortized_cost"])
        for service, amount in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
            writer.writerow([start, end, service, f"{amount:.2f}"])


def main():
    cfg = _config()
    region = (cfg.get("aws") or {}).get("region", "us-east-1")
    ct = cfg.get("cost_tracker") or {}

    start, end = previous_week(ct.get("timezone", "UTC"))
    totals = cost_by_service(
        start, end, region,
        tag_key=ct.get("cost_center_tag_key"),
        tag_values=ct.get("cost_center_tag_values"),
    )

    grand_total = round(sum(totals.values()), 2)
    print(f"AWS cost by service — {start} to {end} ({region})")
    print("-" * 50)
    for service, amount in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
        print(f"{service:<40} {amount:>9.2f}")
    print("-" * 50)
    print(f"{'TOTAL':<40} {grand_total:>9.2f}")

    csv_path = os.environ.get("COST_CSV_PATH", ct.get("csv_path") or f"cost_by_service_{start}_to_{end}.csv")
    write_csv(csv_path, start, end, totals)
    print(f"\nWrote {len(totals)} rows to {csv_path}")


if __name__ == "__main__":
    main()

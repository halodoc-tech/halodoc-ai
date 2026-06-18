# Cost Tracker Automation

Aggregates last week's (Sunday–Saturday) AWS infrastructure costs and performance metrics into
`datalake_config.de_metrics`. Runs weekly via Jenkins — no parameters required.

**Entry point:** `src/cost_tracker_automation/main.py`

---

## Jenkins Job — WeeklyCostTrackerAutomation

- **Job name:** `WeeklyCostTrackerAutomation`
- **Trigger:** Runs automatically on a weekly schedule — no manual trigger required
- **Parameters:** None
- **Manual trigger:** Can be triggered manually if needed (no parameters to fill in — just run the job)

---

## File Structure

```
src/cost_tracker_automation/
  main.py               # Orchestrator: get_de_metrics() + insert_metrics_to_mysql()
  session_manager.py    # MWAASessionManager with JWT caching
  cost_tracking_sql.py  # SQL queries (Spark metrics, Redshift query duration)
  metrics_dictionary.py # Metric category definitions
  variables.py          # DB hosts, Redshift config, AWS service key_dict
```

---

## What It Collects

The job automatically calculates the prior full week (Sun–Sat) and inserts all metrics into
`datalake_config.de_metrics` with columns:
`run_date · environment · category · service_name · metric_name · metric_value · created_at`

| Metric Category | Source | Function |
|---|---|---|
| AWS service costs (by CostCenter tag `DE` / `DE-DS`) | Cost Explorer | `get_datalake_cost()` |
| S3 bucket size + object count | CloudWatch | `get_s3_metric()` |
| S3 API call counts | CloudWatch | `get_s3_api_call()` |
| Redshift query runtime breakdown | CloudWatch | `get_redshift_query_runtime()` |
| Redshift CPU + disk utilisation | CloudWatch | `get_redshift_utilization()` |
| Redshift query duration (Short/Medium/Long) | Redshift SQL | `get_redshift_queries_duration()` |
| MWAA CPU + memory utilisation | CloudWatch | `get_mwaa_utlisations()` |
| DAG success rate (%) | MWAA REST API | `get_dag_success_percentage_in_range()` |
| Spark job metrics | MySQL `spark_app_metrics` | `get_spark_metrics()` |

---

## Answering Cost Questions — With or Without AWS MCP

Use this section when the user asks about DE costs, week-over-week changes, or what drove an increase.

---

### Step 1 — Always: Determine the week reference from Metabase

Run this first regardless of whether AWS MCP is available.

Use **Metabase MCP, DB ID 41** (`datalake_config`, MySQL):

```sql
SELECT
  MAX(run_date) AS latest_run_date,
  -- Current tracked week: starts Sunday, ends Saturday
  DATE_SUB(MAX(run_date), INTERVAL (DAYOFWEEK(MAX(run_date)) - 1) DAY)        AS current_week_start_sunday,
  DATE_ADD(
    DATE_SUB(MAX(run_date), INTERVAL (DAYOFWEEK(MAX(run_date)) - 1) DAY), INTERVAL 6 DAY
  )                                                                             AS current_week_end_saturday,
  -- Prior week: same but 7 days earlier
  DATE_SUB(MAX(run_date), INTERVAL (DAYOFWEEK(MAX(run_date)) - 1) + 7 DAY)    AS prior_week_start_sunday,
  DATE_ADD(
    DATE_SUB(MAX(run_date), INTERVAL (DAYOFWEEK(MAX(run_date)) - 1) + 7 DAY), INTERVAL 6 DAY
  )                                                                             AS prior_week_end_saturday
FROM datalake_config.de_metrics
WHERE environment = 'prod';
```

The result gives you explicit Sunday and Saturday boundaries for both weeks:

| Window | Start | End | Example |
|---|---|---|---|
| **Current tracked week** | `current_week_start_sunday` | `current_week_end_saturday` | 2025-04-13 (Sun) → 2025-04-19 (Sat) |
| **Prior week** | `prior_week_start_sunday` | `prior_week_end_saturday` | 2025-04-06 (Sun) → 2025-04-12 (Sat) |

> **Week definition:** Start = Sunday, End = Saturday. Every tracked week follows this boundary.

> **Cost Explorer end date:** CE uses **exclusive end dates**. Set `End` to the day **after** the Saturday (i.e., the following Sunday). Example: for week ending 2025-04-19 (Sat), use `End = 2025-04-20`.

---

### Step 2a — Without AWS MCP: Service-level costs only

`de_metrics` stores aggregated amortized cost per AWS service. It does **not** store EC2 run hours, S3 API call counts, or Redshift concurrency scaling usage — those are only available via AWS MCP.

```sql
SELECT
  cur.service_name,
  cur.metric_name,
  cur.metric_value  AS current_week,
  prev.metric_value AS prior_week,
  ROUND(cur.metric_value - prev.metric_value, 4) AS delta
FROM datalake_config.de_metrics cur
LEFT JOIN datalake_config.de_metrics prev
  ON  cur.service_name = prev.service_name
  AND cur.metric_name  = prev.metric_name
  AND cur.environment  = prev.environment
  AND prev.run_date    = DATE_SUB(cur.run_date, INTERVAL 7 DAY)
WHERE cur.run_date    = '<latest_run_date>'
  AND cur.environment = 'prod'
  AND cur.category    = 'aws_cost'
ORDER BY ABS(delta) DESC;
```

**What you can answer without AWS MCP:**
- Which AWS service costs more/less than last week
- Total week-over-week cost delta across all DE services

**What requires AWS MCP (not in `de_metrics`):**
- EC2 run hours and which instance type drove the change
- S3 API call counts (GET/PUT/LIST) and which request type drove the cost
- Redshift concurrency scaling usage
- Any usage-level attribution within a service

If the user asks any of these without AWS MCP connected: tell them the service-level cost delta from `de_metrics`, then say: *"For the breakdown of what drove this — instance hours, API calls, or concurrency scaling — I need AWS MCP to query Cost Explorer directly."*

---

### Step 2b — With AWS MCP: Query Cost Explorer for usage-level detail

Use `mcp__awslabs-aws-api__call_aws` with the parameters below. Run **twice** — once for the current tracked week, once for the prior week — then diff the results.

**Service:** `ce` | **Operation:** `get_cost_and_usage`

```json
{
  "TimePeriod": {
    "Start": "<current_week_start_sunday>",
    "End": "<current_week_end_saturday + 1 day>"
  },
  "Granularity": "DAILY",
  "GroupBy": [
    { "Type": "DIMENSION", "Key": "SERVICE" },
    { "Type": "DIMENSION", "Key": "USAGE_TYPE" }
  ],
  "Filter": {
    "Tags": {
      "Key": "CostCenter",
      "Values": ["DE", "DE-DS"]
    }
  },
  "Metrics": ["AmortizedCost", "UsageQuantity"]
}
```

> `End` is the Sunday after the tracked Saturday — CE excludes the end date.

---

### Step 3 — Analyse results for any service

**The general approach applies to every service — not just EC2, S3, or Redshift:**

1. From the CE response, group `AmortizedCost` by `SERVICE` and diff → identifies which services moved
2. For any service that moved significantly, look at its `USAGE_TYPE` breakdown and diff `UsageQuantity` → explains what within that service changed
3. The `USAGE_TYPE` name itself describes the usage (instance type, request tier, node type, DPU hours, etc.) — read it literally to explain the change to the user

**How to read USAGE_TYPE values (general rules):**

| Pattern in USAGE_TYPE | What it means |
|---|---|
| Contains instance type (e.g. `m6g.4xlarge`, `r6g.2xlarge`) | Compute hours for that instance — `UsageQuantity` = hours |
| Contains `concurrency-scaling` | Burst capacity hours billed separately |
| Contains `Requests-Tier1` / `Requests-Tier2` | API request counts — Tier1 (write/list) costs more than Tier2 (read) |
| Contains `Storage` / `ByteHrs` | Storage volume over time — `UsageQuantity` = GB-months |
| Contains `DPU-Hour` | Glue job compute units — `UsageQuantity` = DPU-hours |
| Contains `DataScanned` | Athena bytes scanned — `UsageQuantity` = TB |
| Contains `Node:` | Managed node (Redshift, EMR, etc.) — `UsageQuantity` = node-hours |
| Starts with region prefix (`APS1-`) | Same as above, just region-qualified for ap-southeast-1 |

**Workflow for any cost question:**

```
1. Get de_metrics service-level delta (Step 2a) → find the services that moved
2. If AWS MCP available: run CE query for those services → get USAGE_TYPE breakdown
3. Diff UsageQuantity week-over-week for USAGE_TYPEs within that service
4. The USAGE_TYPE with the largest positive delta = the driver
5. Translate the USAGE_TYPE name into plain English for the user
```

**Example observation output (adapt structure to whatever services are relevant):**

```
Week: 2025-04-13 (Sun) → 2025-04-19 (Sat)  vs  2025-04-06 (Sun) → 2025-04-12 (Sat)

── Service-level from de_metrics ───────────────────────────────────
  Amazon EC2      $1,840 → $2,140  (+$300, +16%)  ← investigate
  Amazon S3         $390 →   $438  (+$48,  +12%)  ← investigate
  Amazon Redshift   $560 →   $605  (+$45,   +8%)
  AWS Glue          $290 →   $278  (-$12,   -4%)
  Amazon DMS         $95 →    $96  (+$1,    +1%)  stable

── USAGE_TYPE breakdown via AWS MCP ────────────────────────────────
Amazon EC2:
  APS1-BoxUsage:m6g.4xlarge  :  340h → 480h  (+140h)  ← main driver
  APS1-BoxUsage:r6g.2xlarge  :  180h → 185h  (+5h)    stable
  APS1-SpotUsage:r6g.2xlarge :   60h →  58h  (-2h)    stable

Amazon S3:
  APS1-Requests-Tier1 (PUT/LIST): 1.2M → 1.8M  (+600K)  ← S3 driver
  APS1-Requests-Tier2 (GET/HEAD): 4.1M → 4.0M  (stable)
  APS1-TimedStorage-ByteHrs     : stable

(Any other service with significant delta gets the same treatment)
```

---

### Handling "current week" when the tracker hasn't run yet

If the user says "this week" but the latest `run_date` is more than 7 days ago, note it:

> *"The cost tracker last ran on {latest_run_date}, covering the week of {week_start} to {week_end}. Data for the current incomplete week is not yet available — the tracker runs every Saturday night."*

---

## Key Class — `MWAASessionManager` (`session_manager.py`)

Manages MWAA REST API authentication with JWT caching in Airflow Variables.

| Method | Description |
|---|---|
| `_create_session()` | Get web token → POST login → Cache in Airflow Variable → Return `(hostname, jwt)` |
| `_load_cached_session()` | Load from Airflow Variable `mwaa_session_info` or return `None` |
| `request(method, path, **kwargs)` | API call with auto-refresh on 401; 3 retries; exponential backoff (2–8s) |

**Session cache key:** Airflow Variable `mwaa_session_info` — JSON `{hostname, jwt_token}`

---

## Databases

| Database | Host | User | DB |
|---|---|---|---|
| MySQL (datalake-config) prod | `datalake-config.<cluster-id>.ap-southeast-1.rds.amazonaws.com` | `<rds-user>` | `datalake_config` |
| Redshift | `<redshift-cluster-name>.<cluster-id>.ap-southeast-1.redshift.amazonaws.com` | `<redshift-user>` | `<redshift-db>` |

---

## Component-Specific Env Vars

| Variable | Required | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID_PROD` | Yes | Prod AWS credentials |
| `AWS_SECRET_ACCESS_KEY_PROD` | Yes | Prod AWS credentials |
| `AWS_SESSION_TOKEN_PROD` | Yes | Prod AWS session token |
| `REDSHIFT_PASSWORD` | Yes | Redshift `<redshift-user>` password |
| `DATALAKE_CONFIG_PASSWORD` | Yes | MySQL `<rds-user>` password |

---

## AWS Services Used

| Service | Purpose |
|---|---|
| Cost Explorer | AWS service costs filtered by `CostCenter: DE` / `DE-DS` tags |
| CloudWatch | S3, Redshift, MWAA metrics; period = weekly (604800s) |
| MWAA REST API | DAG run success rate (`/dags/~/dagRuns`) |
| RDS MySQL | Target: `datalake_config.de_metrics` |
| Redshift | Query duration SQL from `monitoring.redshift_scan_query_metrics` |

---

## SQL Queries (`cost_tracking_sql.py`)

- `spark_de_metrics_sql` — union of 9 aggregations from `spark_app_metrics`
- `redshift_query_duration_sql` — CTE with DATEDIFF-based classification into Short (<10s) / Medium (10–600s) / Long (>600s)

---

## Notes

- `get_datalake_cost()` adds **1 day** to `end_time` — boto3 Cost Explorer excludes the end date
- MWAA utilisation: period must be `604800` (weekly); other periods return empty
- Only `success` and `failed` DAG run states are counted; `running`/`queued` are skipped
- Redshift cluster name is hardcoded in `variables.py` as `<redshift-cluster-name>`

---

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized` on MWAA API | Stale JWT token | `MWAASessionManager` auto-refreshes; check AWS creds |
| Cost data shows $0 | `CostCenter` tag missing on AWS resources | Verify resources tagged `CostCenter: DE` |
| `mwaa_utlisations` returns empty | CloudWatch period mismatch | Period must be `604800`; check time range |
| Redshift query times out | Long-running aggregation | Schedule at off-peak or increase timeout |

---

## Tests

`tests/cost_tracker_automation/test_session_manager.py`
- `MWAASessionManager` session creation and caching
- 401 auto-refresh behavior
- Retry logic with exponential backoff
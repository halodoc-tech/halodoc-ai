spark_de_metrics_sql = '''
SELECT
    '1 Total Memory Used (in TB)' AS metrics_name,
--     round(SUM(executor_memory)/1024/1024/1024/1024,2) AS metrics_value,
    round(2 * SUM(max_memory)/1024/1024/1024/1024,2)AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
 UNION ALL 
 SELECT
    '2 Total Cores' AS metrics_name,
    SUM(total_cores) AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
UNION ALL
SELECT
    '3 Total Number of Jobs Runs' AS metrics_name,
    COUNT(DISTINCT app_id) AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
UNION ALL
SELECT
    '4 Total Execution time (in hr)' AS metrics_name,
    round(SUM(app_duration)/60/60/1000,2) AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
UNION ALL
SELECT
    '5 Total Input Records read (in GB)' AS metrics_name,
    round(SUM(total_input_bytes_read)/1024/1024/1024,2) AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
UNION ALL
SELECT
    '6 Total Output Records written(in GB)' AS metrics_name,
    round(SUM(total_output_bytes_written)/1024/1024/1024,2) AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
UNION ALL
SELECT
    '7 Number Spot instances deleted' AS metrics_name,
    COUNT(*) AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
  AND exec_loss_reason LIKE '%was deleted by a user or the framework.'
UNION ALL
SELECT
    '8 Tasks OOM' AS metrics_name,
    COUNT(*) AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
  AND exec_loss_reason LIKE '%OOM%'
UNION ALL
SELECT
    '9 Task Sucess Rate' AS metrics_name,
    100.0 - (SUM(total_failed_tasks) * 100 / NULLIF(SUM(total_completed_tasks), 0)) AS metrics_value
FROM datalake_config.spark_app_metrics
WHERE created_at >= '{START_DATE}'
  AND created_at <= '{END_DATE}'
ORDER BY 1
'''

redshift_query_duration_sql = '''
with monitoring as (
select
    query,
    query_start_time,
    datediff(
        second,
        query_start_time,
        query_end_time
    ) AS diff_in_seconds,
    DATEDIFF(
        minute,
        query_start_time,
        query_end_time
    ) AS diff_in_minutes,
    case
        when diff_in_seconds < 10 then 'short_query'
        when diff_in_seconds >= 10 and diff_in_seconds <= 600 then 'medium_query'
        when diff_in_seconds > 600 then 'long_query'
    end as query_duration
from monitoring.redshift_scan_query_metrics
where query_start_time >= '{START_DATE}'
    and query_end_time <= '{END_DATE}'
)
select
    'Short Query Count' as query_type,
    count(distinct query) as short_query_count
from
    monitoring
where query_duration = 'short_query'
union all
select
    'Medium Query Count' as query_type,
    count(distinct query) as medium_query_count
from
    monitoring
where query_duration = 'medium_query'
union all
select
    'Long Query Count' as query_type,
    count(distinct query) as long_query_count
from
    monitoring
where query_duration = 'long_query'
'''

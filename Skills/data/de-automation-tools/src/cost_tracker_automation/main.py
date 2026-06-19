import os

import psycopg2
import pytz
from datetime import datetime, timezone, timedelta
import boto3
import logging

from variables import *
from metrics_dictionary import s3_storage_metrics, s3_api_call, redshift_execution_metrics
from session_manager import mwaa_session
import mysql
import mysql.connector
import requests
import re
from cost_tracking_sql import *

logger = logging.getLogger(__name__)

def get_env_variables():
    """
    Get the environment variables from Jenkins
    :return:
    """
    return {
        "region_name": "ap-southeast-1",
        "prod": {
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID_PROD"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY_PROD"),
            "aws_session_token": os.getenv("AWS_SESSION_TOKEN_PROD"),
        },
        "stage": {
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID_STAGE"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY_STAGE"),
            "aws_session_token": os.getenv("AWS_SESSION_TOKEN_STAGE"),
        }
    }


def get_datalake_cost(start_time, end_time, env):
    """
    Get the cost of the datalake for the given environment
    :param start_time:
    :param end_time:
    :param env: stage/prod
    :return: service_cost_dict and total_cost
    """
    aws_creds = get_env_variables()
    if env == 'prod':
        cost_client = boto3.client('ce', region_name=aws_creds['region_name'],
                                   aws_access_key_id=aws_creds['prod']['aws_access_key_id'],
                                   aws_secret_access_key=aws_creds['prod']['aws_secret_access_key'],
                                   aws_session_token=aws_creds['prod']['aws_session_token'])
    elif env == 'stage':
        cost_client = boto3.client('ce', region_name=aws_creds['region_name'],
                                   aws_access_key_id=aws_creds['stage']['aws_access_key_id'],
                                   aws_secret_access_key=aws_creds['stage']['aws_secret_access_key'],
                                   aws_session_token=aws_creds['stage']['aws_session_token'])
    else:
        raise Exception("Invalid environment")
    end_time = str((datetime.strptime(end_time, '%Y-%m-%d') + timedelta(days=1)).strftime(
        '%Y-%m-%d'))  # Increasing one day as boto3 cost explorer Excludes the last date mentioned
    response = cost_client.get_cost_and_usage(  # Same filters we apply on AWS Cost Explorer applied here
        TimePeriod={
            'Start': start_time,
            'End': end_time
        },
        Granularity='DAILY',
        Metrics=['AmortizedCost'],
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'SERVICE'
            },
        ],
        Filter={
            "Or": [
                {
                    "Tags": {
                        "Key": "CostCenter",
                        "Values": [
                            "DE",
                            "DE-DS"
                        ],
                        "MatchOptions": ["EQUALS"]
                    }
                },
                {
                    "Tags": {
                        "Key": "CostCenter",
                        "MatchOptions": ["ABSENT"]
                    }
                }
            ]
        }
    )
    # print(response)
    total_cost = 0
    service_cost_dict = {}
    for result_by_time in response['ResultsByTime']:
        for group in result_by_time['Groups']:
            service_name = group['Keys'][0]  # Extract the service name
            cost = round(float(group['Metrics']['AmortizedCost']['Amount']), 2)  # Extract the cost
            if service_name not in service_cost_dict:
                service_cost_dict[service_name] = 0.0
            service_cost_dict[service_name] += cost
            total_cost += cost

    return service_cost_dict, total_cost


def datetime_iso(tz_name="UTC"):
    """
    Generate the start and end timestamps (ISO format) for the previous week's Sunday to Saturday period.
    Args:
        tz_name (str): Timezone name (default is "UTC"). The function will localize the timestamps accordingly.
    Returns:
        tuple: A tuple containing two ISO 8601 formatted datetime strings:
            - Start time: 00:00:00 on the Sunday of the previous week.
            - End time: 23:59:59 on the Saturday of the previous week.
    Example:
        # >>> datetime_iso("Asia/Jakarta")
        ('2024-02-04T00:00:00+07:00', '2024-02-10T23:59:59+07:00')
    Notes:
        - The function determines the most recent Sunday from the current date and calculates the previous week's range.
        - The result is localized to the specified timezone.
    """
    tz = pytz.timezone(tz_name)
    time_now = datetime.now(timezone.utc).astimezone(tz)

    days_to_sunday = time_now.weekday() + 1
    sunday_this_week = time_now - timedelta(days=days_to_sunday)
    sunday_last_week = sunday_this_week - timedelta(weeks=1)
    saturday_last_week = sunday_last_week + timedelta(days=6)

    start_time = tz.localize(datetime(sunday_last_week.year, sunday_last_week.month, sunday_last_week.day, 0, 0, 0))
    end_time = tz.localize(
        datetime(saturday_last_week.year, saturday_last_week.month, saturday_last_week.day, 23, 59, 59))

    return start_time.isoformat(), end_time.isoformat()


def get_s3_api_call(env, metric_name, filter_id, bucket_name, start_time, end_time):
    """
      Fetches S3 API call metrics from AWS CloudWatch for a specified bucket and time period.
    Args:
        env (str): The environment ('prod' or 'stage') to determine AWS credentials.
        metric_name (str): The name of the CloudWatch metric to retrieve (e.g., 'NumberOfObjects', 'BucketSizeBytes').
        filter_id (str): The filter ID used in CloudWatch dimensions to refine the metric.
        bucket_name (str): The name of the S3 bucket for which the metric is being retrieved.
        start_time (datetime): The start time for fetching metric data.
        end_time (datetime): The end time for fetching metric data.
    Returns:
        float: The total sum of the requested metric within the given time range.
               Returns None if no data points are found.
    """
    aws_creds = get_env_variables()
    if env == 'prod':
        e_region_name = aws_creds['region_name']
        e_aws_access_key_id = aws_creds['prod']['aws_access_key_id']
        e_aws_secret_access_key = aws_creds['prod']['aws_secret_access_key']
        e_aws_session_token = aws_creds['prod']['aws_session_token']
    elif env == 'stage':
        e_region_name = aws_creds['region_name']
        e_aws_access_key_id = aws_creds['stage']['aws_access_key_id']
        e_aws_secret_access_key = aws_creds['stage']['aws_secret_access_key']
        e_aws_session_token = aws_creds['stage']['aws_session_token']
    else:
        raise Exception(f'env not found')
    s3 = boto3.client(
        'cloudwatch', region_name=e_region_name,
        aws_access_key_id=e_aws_access_key_id,
        aws_secret_access_key=e_aws_secret_access_key,
        aws_session_token=e_aws_session_token
    )
    response = s3.get_metric_statistics(
        Namespace='AWS/S3',
        Dimensions=[
            {'Name': 'BucketName', 'Value': bucket_name},
            {'Name': 'FilterId', 'Value': filter_id},
        ],
        MetricName=metric_name,
        StartTime=start_time,
        EndTime=end_time,
        Period=86400,
        Statistics=['Sum'],
        Unit='Count'
    )
    if response['Datapoints']:
        total_sum = sum(data_point['Sum'] for data_point in response['Datapoints'])
        return total_sum


def rounded(num, unit):
    """
    Rounds and converts a given numerical value based on the specified unit.
    Args:
        num (float | int): The number to be converted and rounded.
        unit (str): The unit to convert the number into. Supported units:
    Returns:
        float: The rounded value after conversion.
    """
    if unit == 'million':
        return round(num / 1.0e6, 2)
    if unit == 'terabyte':
        return round(num / 1.0e12, 2)
    if unit == 'gigabyte':
        return round(num / 1.0e09, 2)
    if unit == 'time':
        return round(num, 2)


def get_s3_metric(start_time, end_time, env, metric_name, storage_type, bucket_name, get_last_record=False):
    """
       Fetches S3 storage metrics from AWS CloudWatch for a specified bucket and time period.

       Args:
           start_time (datetime): The start time for fetching metric data.
           end_time (datetime): The end time for fetching metric data.
           env (str): The environment ('prod' or 'stage') to determine AWS credentials.
           metric_name (str): The name of the CloudWatch metric to retrieve (e.g., 'BucketSizeBytes', 'NumberOfObjects').
           storage_type (str): The type of storage to filter by (e.g., 'StandardStorage', 'Glacier', 'IntelligentTiering').
           bucket_name (str): The name of the S3 bucket for which the metric is being retrieved.
           get_last_record (bool, optional): If True, returns only the latest data point. Defaults to False.

       Returns:
           dict | list[dict] | None:
               - If `get_last_record=True`, returns the latest data point as a dictionary.
               - Otherwise, returns a list of all available data points.
               - Returns None if no data points are found.
    """
    aws_creds = get_env_variables()
    if env == 'prod':
        e_region_name = aws_creds['region_name']
        e_aws_access_key_id = aws_creds['prod']['aws_access_key_id']
        e_aws_secret_access_key = aws_creds['prod']['aws_secret_access_key']
        e_aws_session_token = aws_creds['prod']['aws_session_token']
    elif env == 'stage':
        e_region_name = aws_creds['region_name']
        e_aws_access_key_id = aws_creds['stage']['aws_access_key_id']
        e_aws_secret_access_key = aws_creds['stage']['aws_secret_access_key']
        e_aws_session_token = aws_creds['stage']['aws_session_token']
    else:
        raise Exception(f'env not found', {metric_name, storage_type, bucket_name})

    s3 = boto3.client(
        'cloudwatch',
        region_name=e_region_name,
        aws_access_key_id=e_aws_access_key_id,
        aws_secret_access_key=e_aws_secret_access_key,
        aws_session_token=e_aws_session_token
    )

    response = s3.get_metric_statistics(
        Namespace='AWS/S3',
        MetricName=metric_name,
        Dimensions=[
            {'Name': 'BucketName', 'Value': bucket_name},
            {'Name': 'StorageType', 'Value': storage_type},
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=86400,
        Statistics=['Sum'],
    )
    if response['Datapoints']:
        if get_last_record:
            latest_data = max(response['Datapoints'], key=lambda x: x['Timestamp'])
            return latest_data
        else:
            return response['Datapoints']


def get_s3_metrics_summary(start_time, end_time):
    """
    Get the summary of S3 metrics for the given time period
    :param start_time:
    :param end_time:
    :return: summary: dict containing the summary of S3 metrics
    """
    s3_api = s3_api_call  # s3_api_call is a list of dictionaries containing the s3 api call metrics

    for s3_api_metric in s3_api:
        s3_api_data = get_s3_api_call(s3_api_metric['env'], s3_api_metric['name'], s3_api_metric['filter_id'],
                                      s3_api_metric['bucket'], start_time, end_time)
        s3_api_metric['result'] = s3_api_data

    s3_api_metric_result = {m['key']: m['result'] for m in s3_api}

    prod_raw_api_call = [
        s3_api_metric_result['allrequest_raw_example_datalake_prod'],
        s3_api_metric_result['allrequest_raw_example_datalake_prod_raw'],
    ]
    prod_processed_api_call = [
        s3_api_metric_result['allrequest_processed_example_datalake_prod_processed'],
        s3_api_metric_result['allrequest_processed_example_datalake_prod_raw'],
    ]
    sum_prod_raw_api_call = rounded(sum(prod_raw_api_call), 'million')
    sum_prod_processed_api_call = rounded(sum(prod_processed_api_call), 'million')

    s3_storage = s3_storage_metrics
    for s3_storage_metric in s3_storage:
        data = get_s3_metric(start_time=start_time, end_time=end_time, env=s3_storage_metric['env'],
                             metric_name=s3_storage_metric['name'],
                             storage_type=s3_storage_metric['storage_type'], bucket_name=s3_storage_metric['bucket'],
                             get_last_record=True)
        result = data['Sum'] if data and 'Sum' in data else 0
        s3_storage_metric['result'] = result

    s3_storage_metric_results = {m['key']: m['result'] for m in s3_storage}
    prod_s3_datasize = [  # List of all the s3 storage metrics to be included in the summary
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod_raw'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod_processed'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_standardiastorage_example_datalake_prod'],
        s3_storage_metric_results['bucketsizebytes_glacierinstantretrievalstorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_standardiastorage_example_datalake_prod_raw'],
        s3_storage_metric_results['bucketsizebytes_standardiastorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringfastaccessstorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringfastaccessstorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringfastaccessstorage_example_datalake_prod_raw'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringinfrequentaccessstorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringinfrequentaccessstorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringaiastorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringaiastorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringaastorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringinfrequentaccessstorage_example_datalake_prod_raw'],
    ]

    prod_s3_standard_storage = [
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod_raw'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod_processed'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_prod_archive'],
    ]

    prod_s3_non_standard_storage = [
        s3_storage_metric_results['bucketsizebytes_standardiastorage_example_datalake_prod'],
        s3_storage_metric_results['bucketsizebytes_glacierinstantretrievalstorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_standardiastorage_example_datalake_prod_raw'],
        s3_storage_metric_results['bucketsizebytes_standardiastorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringfastaccessstorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringfastaccessstorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringfastaccessstorage_example_datalake_prod_raw'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringinfrequentaccessstorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringinfrequentaccessstorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringaiastorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringaiastorage_example_datalake_prod_backup'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringaastorage_example_datalake_prod_archive'],
        s3_storage_metric_results['bucketsizebytes_intelligenttieringinfrequentaccessstorage_example_datalake_prod_raw'],
    ]

    prod_number_object = [
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_prod'],
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_prod_backup'],
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_prod_raw'],
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_prod_processed'],
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_prod_archive'],
    ]

    stage_s3_datasize = [
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_stage'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_stage_raw'],
        s3_storage_metric_results['bucketsizebytes_standardiasizeoverhead_example_datalake_stage'],
        s3_storage_metric_results['bucketsizebytes_standardiastorage_example_datalake_stage'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_stage_backup'],
        s3_storage_metric_results['bucketsizebytes_glacierinstantretrievalstorage_example_datalake_stage_backup'],
        s3_storage_metric_results['bucketsizebytes_standardiasizeoverhead_example_datalake_stage_raw'],
        s3_storage_metric_results['bucketsizebytes_standardiastorage_example_datalake_stage_raw'],
        s3_storage_metric_results['bucketsizebytes_standardstorage_example_datalake_stage_archive'],
        s3_storage_metric_results['bucketsizebytes_allstoragetypes_example_datalake_stage_processed']
    ]

    stage_number_object = [
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_stage_raw'],
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_stage_backup'],
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_stage'],
        s3_storage_metric_results['numberofobjects_allstoragetypes_example_datalake_stage_processed']

    ]
    sum_prod_s3_datasize = rounded(sum(prod_s3_datasize), 'terabyte')
    sum_prod_s3_standart_storage = rounded(sum(prod_s3_standard_storage), 'terabyte')
    sum_prod_prod_s3_non_standard_storage = rounded(sum(prod_s3_non_standard_storage), 'terabyte')
    sum_prod_number_object = rounded(sum(prod_number_object), 'million')
    sum_stage_number_object = rounded(sum(stage_number_object), 'million')
    sum_stage_s3_datasize = rounded(sum(stage_s3_datasize), 'gigabyte')

    summary = {
        'sum_prod_s3_datasize': sum_prod_s3_datasize,
        'sum_prod_s3_standard_storage': sum_prod_s3_standart_storage,
        'sum_prod_prod_s3_non_standard_storage': sum_prod_prod_s3_non_standard_storage,
        'sum_prod_number_object': sum_prod_number_object,
        'sum_prod_raw_api_call': sum_prod_raw_api_call,
        'sum_prod_processed_api_call': sum_prod_processed_api_call,
        'sum_stage_number_object': sum_stage_number_object,
        'sum_stage_s3_datasize': sum_stage_s3_datasize
    }
    return summary


def get_redshift_query_runtime(metric, start_time, end_time):
    """
    Get the runtime of the given metric for the given time period
    :param metric:
    :param start_time:
    :param end_time:
    :return: response: dict containing the runtime average of the given metric
    """
    aws_creds = get_env_variables()
    cluster_id = redshift_cluster_name
    namespace = "AWS/Redshift"

    redshift = boto3.client(
        'cloudwatch', region_name=aws_creds['region_name'],
        aws_access_key_id=aws_creds['prod']['aws_access_key_id'],
        aws_secret_access_key=aws_creds['prod']['aws_secret_access_key'],
        aws_session_token=aws_creds['prod']['aws_session_token']
    )
    response = redshift.get_metric_statistics(
        Namespace=namespace,
        MetricName="QueryRuntimeBreakdown",
        Dimensions=[
            {"Name": "stage", "Value": metric},
            {"Name": "ClusterIdentifier", "Value": cluster_id},
        ],

        StartTime=start_time,
        EndTime=end_time,
        Period=86400,
        Statistics=['Average']
    )
    return response


def get_redshift_utilization(metric, start_time, end_time):
    """
    Get the utilization of the given metric for the given time period
    :param metric:
    :param start_time:
    :param end_time:
    :return: response: dict containing the utilization of the given metric
    """
    aws_creds = get_env_variables()
    cluster_id = redshift_cluster_name
    namespace = "AWS/Redshift"

    redshift = boto3.client(
        'cloudwatch', region_name=aws_creds['region_name'],
        aws_access_key_id=aws_creds['prod']['aws_access_key_id'],
        aws_secret_access_key=aws_creds['prod']['aws_secret_access_key'],
        aws_session_token=aws_creds['prod']['aws_session_token']
    )
    response = redshift.get_metric_data(
        MetricDataQueries=[
            {
                "Id": metric.lower(),
                "MetricStat": {
                    "Metric": {
                        "Namespace": namespace,
                        "MetricName": metric,
                        "Dimensions": [{"Name": "ClusterIdentifier", "Value": cluster_id}],
                    },
                    "Period": 86400,
                    "Stat": "Average",
                },
                "ReturnData": True,
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
    )
    return response["MetricDataResults"][0] if response["MetricDataResults"] else None


def get_redshift_queries_duration(start_time, end_time):
    """
    Get the duration of the Redshift queries and sort it like short,medium and long running queries for the given time period
    :param start_time:
    :param end_time:
    :return: redshift_query_duration_dict: dict containing the duration of the Redshift queries
    """
    query = redshift_query_duration_sql.format(START_DATE=start_time, END_DATE=end_time)
    print("\nRedshift query duration Query: \n", query, "\n")
    conn = None
    try:
        conn = psycopg2.connect(
            host=redshift_host,
            user=redshift_user,
            password=os.environ['REDSHIFT_PASSWORD'],
            port=redshift_port,
            dbname=redshift_dbname
        )
        cur = conn.cursor()

        cur.execute(query)

        results = cur.fetchall()  # Fetch all results
        redshift_query_duration_dict = {}
        if results:
            for row in results:
                redshift_query_duration_dict[row[0]] = row[1]
            return redshift_query_duration_dict
        else:
            raise Exception("No data found")
    except (Exception, psycopg2.Error) as error:
        raise Exception(f"Error while fetching data from Redshift: {error}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_redshift_metrics_summary(start_time, end_time):
    """
    Get the summary of Redshift metrics for the given time period
    :param start_time:
    :param end_time:
    :return: redshift_summary: dict containing the summary of Redshift metrics
    """
    get_redshift_wait_time = get_redshift_query_runtime('QueryWaiting', start_time, end_time)
    redshift_wait_time_sec = [d['Average'] / 1000 for d in get_redshift_wait_time['Datapoints']]
    average_redshift_wait_time = round((sum(redshift_wait_time_sec) / len(redshift_wait_time_sec)) / 60, 2)

    # redshift execution time
    redshift_execution_metric = redshift_execution_metrics  # This is a list of redshift execution metrics
    total_execution_seconds = 0
    for metric in redshift_execution_metric:
        exec_time_all = get_redshift_query_runtime(metric, start_time, end_time)
        total_execution_seconds += sum(d['Average'] / 1000 for d in exec_time_all['Datapoints'])
    average_execution_seconds = round((total_execution_seconds / 60) / 7, 2)

    cpu_utilization = get_redshift_utilization("CPUUtilization", start_time, end_time)
    disk_space_used = get_redshift_utilization("PercentageDiskSpaceUsed", start_time, end_time)
    average_cpu_utilization = round(sum(cpu_utilization['Values']) / len(cpu_utilization['Values']), 2)
    disk_space_used = round(sum(disk_space_used['Values']) / len(disk_space_used['Values']), 2)

    redshift_query_duration_dict = get_redshift_queries_duration(start_time, end_time)
    redshift_data_scanned = get_redshift_data_scanned(start_time, end_time)
    redshift_summary = {
        'average_redshift_wait_time': average_redshift_wait_time,
        'average_execution_seconds': average_execution_seconds,
        'average_cpu_utilization': average_cpu_utilization,
        'disk_space_used': disk_space_used,
        'short_queries': redshift_query_duration_dict['Short Query Count'],
        'medium_queries': redshift_query_duration_dict['Medium Query Count'],
        'long_queries': redshift_query_duration_dict['Long Query Count'],
        'aps1_data_scanned': redshift_data_scanned
    }
    return redshift_summary


def get_cursor():
    """
    Get the cursor for the datalake_config database
    :return:
    """
    host = datalake_host
    port = datalake_port
    uname = datalake_uname
    pwd = os.environ['DATALAKE_CONFIG_PASSWORD']
    db = datalake_db
    conn = mysql.connector.connect(
        host=host,
        user=uname,
        password=pwd,
        database=db,
        port=port
    )
    return conn


def get_spark_metrics(start_time, end_time):
    """
    Get the summary of Spark metrics for the given time period from the datalake_config database
    :param start_time:
    :param end_time:
    :return: result_dict: dict containing the summary of Spark metrics
    """
    query = spark_de_metrics_sql.format(START_DATE=start_time, END_DATE=end_time)
    print("\n\n\n\n\nSPARK METRICS Query:", query)
    conn = get_cursor()
    cur = conn.cursor()
    cur.execute(query)
    result = cur.fetchall()
    if result:
        result_dict = {row[0]: float(row[1]) for row in result}
        return result_dict
    else:
        raise Exception("No data found")


def get_mwaa_utlisations(start_time, end_time):
    """
    Get the MWAA utilizations for the given time period from cloudwatch on weekly aggregation
    Args:
        start_time:
        end_time:

    Returns: avg_cpu_utilization, avg_memory_utilization (float, float)

    """
    aws_creds = get_env_variables()
    cloudwatch = boto3.client("cloudwatch", region_name=aws_creds['region_name'],
                              aws_access_key_id=aws_creds['prod']['aws_access_key_id'],
                              aws_secret_access_key=aws_creds['prod']['aws_secret_access_key'],
                              aws_session_token=aws_creds['prod']['aws_session_token'])
    metric_queries = [
        {
            "Id": "m1",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/MWAA",
                    "MetricName": "CPUUtilization",
                    "Dimensions": [
                        {"Name": "Cluster", "Value": "AdditionalWorker"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,  # weekly Aggregation
                "Stat": "Average",
            },
            "ReturnData": True,
        },
        {
            "Id": "m2",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/MWAA",
                    "MetricName": "CPUUtilization",
                    "Dimensions": [
                        {"Name": "Cluster", "Value": "WebServer"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,
                "Stat": "Average",
            },
            "ReturnData": True,
        },
        {
            "Id": "m3",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/MWAA",
                    "MetricName": "CPUUtilization",
                    "Dimensions": [
                        {"Name": "Cluster", "Value": "BaseWorker"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,
                "Stat": "Average",
            },
            "ReturnData": True,
        },
        {
            "Id": "m4",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/MWAA",
                    "MetricName": "CPUUtilization",
                    "Dimensions": [
                        {"Name": "Cluster", "Value": "Scheduler"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,
                "Stat": "Average",
            },
            "ReturnData": True,
        },
        {
            "Id": "m5",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/MWAA",
                    "MetricName": "MemoryUtilization",
                    "Dimensions": [
                        {"Name": "Cluster", "Value": "BaseWorker"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,
                "Stat": "Average",
            },
            "ReturnData": True,
        },
        {
            "Id": "m6",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/MWAA",
                    "MetricName": "MemoryUtilization",
                    "Dimensions": [
                        {"Name": "Cluster", "Value": "WebServer"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,
                "Stat": "Average",
            },
            "ReturnData": True,
        },
        {
            "Id": "m7",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/MWAA",
                    "MetricName": "MemoryUtilization",
                    "Dimensions": [
                        {"Name": "Cluster", "Value": "Scheduler"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,
                "Stat": "Average",
            },
            "ReturnData": True,
        },
        {
            "Id": "m8",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/MWAA",
                    "MetricName": "MemoryUtilization",
                    "Dimensions": [
                        {"Name": "Cluster", "Value": "AdditionalWorker"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,
                "Stat": "Average",
            },
            "ReturnData": True,
        },
        {
            "Id": "m9",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AmazonMWAA",
                    "MetricName": "SchedulerLoopDuration",
                    "Dimensions": [
                        {"Name": "Function", "Value": "Scheduler"},
                        {"Name": "Environment", "Value": prod_airflow_env_name}
                    ],
                },
                "Period": 604800,
                "Stat": "Maximum",  # p99 is not available for this metric in MWAA
            },
            "ReturnData": True,
        },
    ]
    response = cloudwatch.get_metric_data(
        MetricDataQueries=metric_queries,
        StartTime=start_time,
        EndTime=end_time
    )
    # print(response)
    avg_cpu_utilization = 0.0
    avg_memory_utilization = 0.0
    scheduler_loop_duration = None
    for metric_data_result in response["MetricDataResults"]:
        if metric_data_result["Id"] in ("m1", "m2", "m3", "m4"):
            avg_cpu_utilization += metric_data_result["Values"][0]
        elif metric_data_result["Id"] in ("m5", "m6", "m7", "m8"):
            avg_memory_utilization += metric_data_result["Values"][0]
        elif metric_data_result["Id"] == "m9" and metric_data_result["Values"]:
            scheduler_loop_duration = round(metric_data_result["Values"][0] / 60000, 2)  # convert ms to minutes
    avg_cpu_utilization /= 4
    avg_memory_utilization /= 4
    return round(avg_cpu_utilization, 2), round(avg_memory_utilization, 2), scheduler_loop_duration


def get_dag_success_percentage_in_range(
    start_time: datetime,
    end_time: datetime,
    max_dag_runs_per_request: int = 500
) -> float:
    try:
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time.split("T")[0], "%Y-%m-%d")
        if isinstance(end_time, str):
            end_time = datetime.strptime(end_time.split("T")[0], "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            
        start_iso = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        offset = 0
        all_dag_runs = []

        while True:
            params = {
                "limit": max_dag_runs_per_request,
                "offset": offset,
                "logical_date_gte": start_iso,
                "logical_date_lte": end_iso,
                "order_by": "-logical_date"
            }

            response = mwaa_session.request(
                "GET",
                "/dags/~/dagRuns",
                params=params,
            )

            data = response.json()
            dag_runs = data.get("dag_runs", [])

            if not dag_runs:
                break

            all_dag_runs.extend(dag_runs)

            logger.info(
                "Fetched %d DAG runs (offset=%d)",
                len(dag_runs), offset
            )

            if len(dag_runs) < max_dag_runs_per_request:
                break

            offset += max_dag_runs_per_request

        if not all_dag_runs:
            logger.warning(
                "No DAG runs found between %s and %s",
                start_iso, end_iso
            )
            return 0.0

        # ✅ Only consider finished runs
        finished_runs = [
            r for r in all_dag_runs if r.get("state") in ["success", "failed"]
        ]

        if not finished_runs:
            logger.info(
                "No finished DAG runs found between %s and %s",
                start_iso, end_iso
            )
            return 0.0

        success_runs = sum(
            1 for run in finished_runs if run.get("state") == "success"
        )

        success_percentage = (success_runs / len(finished_runs)) * 100

        logger.info(
            "GLOBAL DAG METRICS | Total Runs: %d | Finished: %d | Success: %d | Success %%: %.2f",
            len(all_dag_runs),
            len(finished_runs),
            success_runs,
            success_percentage
        )

        return round(success_percentage, 2)

    except Exception as e:
        logger.error(
            "Error calculating global DAG success percentage: %s",
            str(e)
        )
        return 0.0

def get_mwaa_metrics(start_time, end_time):
    """
    Orchestrator function to fetch MWAA metrics:
    - Global DAG success percentage
    - Average CPU utilisation
    - Average memory utilisation
    - Scheduler loop duration (Maximum)
    """

    try:
        success_percentage = get_dag_success_percentage_in_range(
            start_time=start_time,
            end_time=end_time
        )
    except Exception as e:
        logger.warning(
            "Failed to compute DAG success percentage for range %s - %s: %s",
            start_time, end_time, str(e)
        )
        success_percentage = None

    try:
        avg_cpu_utilisation, avg_memory_utilisation, scheduler_loop_duration = get_mwaa_utlisations(
            start_time, end_time
        )
    except Exception as e:
        logger.warning(
            "Failed to fetch MWAA utilisation metrics for range %s - %s: %s",
            start_time, end_time, str(e)
        )
        avg_cpu_utilisation = None
        avg_memory_utilisation = None
        scheduler_loop_duration = None

    return {
        'success_percentage': success_percentage,
        'avg_cpu_utilisation': avg_cpu_utilisation,
        'avg_memory_utilisation': avg_memory_utilisation,
        'scheduler_loop_duration': scheduler_loop_duration,
    }


def get_standard_cost_s3(start_time, end_time):
    """
    Get the standard cost of S3 for the given time period
    :param start_time:
    :param end_time:
    :return: standard_storage_cost: cost of standard storage, total_cost: total cost of S3
    """
    aws_creds = get_env_variables()
    end_time = datetime.strptime(end_time, '%Y-%m-%d') + timedelta(
        days=1)  # add 1 day from end time which was increased for boto3 exclusion
    end_time = end_time.strftime('%Y-%m-%d')
    # print(start_time, end_time)
    cost_client = boto3.client('ce', region_name=aws_creds['region_name'],
                               aws_access_key_id=aws_creds['prod']['aws_access_key_id'],
                               aws_secret_access_key=aws_creds['prod']['aws_secret_access_key'],
                               aws_session_token=aws_creds['prod']['aws_session_token'])
    response = cost_client.get_cost_and_usage(
        TimePeriod={
            'Start': start_time,
            'End': str(end_time)
        },
        Granularity='DAILY',
        Metrics=['AmortizedCost'],
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'OPERATION'
            },
        ],
        Filter={

            "Dimensions": {
                "Key": "SERVICE",
                "Values": [
                    "Amazon Simple Storage Service"
                ],
                "MatchOptions": ["EQUALS"]
            }

        }
    )
    standard_storage_cost = 0.0
    total_cost = 0.0
    for time_period in response['ResultsByTime']:
        for group in time_period['Groups']:
            amount = float(group['Metrics']['AmortizedCost']['Amount'])
            if group['Keys'][0] == 'StandardStorage':
                standard_storage_cost += amount
            total_cost += round(amount, 5)

    return standard_storage_cost, total_cost


def get_redshift_data_scanned(start_time, end_time):
    """
    Get the data scanned by Redshift for the given time period with APS1 API Calls
    :param start_time:
    :param end_time:
    :return:
    """
    aws_creds = get_env_variables()
    end_time = datetime.strptime(end_time, '%Y-%m-%d') + timedelta(
        days=1)  # add 1 day from end time which was increased for boto3 cost explorer exclusion
    end_time = end_time.strftime('%Y-%m-%d')
    cost_client = boto3.client('ce', region_name=aws_creds['region_name'],
                               aws_access_key_id=aws_creds['prod']['aws_access_key_id'],
                               aws_secret_access_key=aws_creds['prod']['aws_secret_access_key'],
                               aws_session_token=aws_creds['prod']['aws_session_token']
                               )
    response = cost_client.get_cost_and_usage(
        TimePeriod={
            'Start': start_time,
            'End': str(end_time)
        },
        Granularity='MONTHLY',
        Metrics=['UsageQuantity'],
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'USAGE_TYPE'
            },
        ],
        Filter={

            "Dimensions": {
                "Key": "SERVICE",
                "Values": [
                    "Amazon Redshift"
                ],
                "MatchOptions": ["EQUALS"]
            }

        }
    )
    data_scanned = response['ResultsByTime'][0]['Groups'][2]['Metrics']['UsageQuantity']['Amount']
    return data_scanned


def get_de_metrics(start_time, end_time, s3_summary, redshift_summary):
    """
    Get the summary of Data Engineering metrics for the given time period
    :param start_time:
    :param end_time:
    :param s3_summary:
    :param redshift_summary:
    :return: de_metrics_summary: dict containing the summary of all Data Engineering metrics
    """
    de_spark_metrics = get_spark_metrics(start_time, end_time)
    mwaa_metrics = get_mwaa_metrics(start_time, end_time)
    s3_standard_cost, total_cost = get_standard_cost_s3(start_time, end_time)
    s3_total_api_calls = s3_summary['sum_prod_raw_api_call'] + s3_summary[
        'sum_prod_processed_api_call']  # Total API calls
    s3_non_standard_cost = float(total_cost) - float(s3_standard_cost)  # Non standard cost
    s3_metrics = {
        'sum_prod_s3_datasize': s3_summary['sum_prod_s3_datasize'],
        'sum_prod_number_object': s3_summary['sum_prod_number_object'],
        's3_total_api_calls': s3_total_api_calls,
        's3_standard_cost': float(s3_standard_cost),
        's3_non_standard_cost': s3_non_standard_cost,
        's3_total_cost': total_cost
    }
    redshift_data_scanned = get_redshift_data_scanned(start_time, end_time)
    redshift_metrics = {
        'CPU(in %)': redshift_summary['average_cpu_utilization'],
        'Avg. Query Wait time ( in mins)': redshift_summary['average_redshift_wait_time'],
        'Avg. Query Execution time (in mins)': redshift_summary['average_execution_seconds'],
        'Long Running query count': redshift_summary['long_queries'],
        'Avg Disk Utilization': redshift_summary['disk_space_used'],
        'Total queries': redshift_summary['short_queries'] + redshift_summary['medium_queries'] + redshift_summary[
            'long_queries'],
        'APS1-DataScanned (TB)': redshift_data_scanned
    }
    de_metrics_summary = {
        'spark_metrics': [de_spark_metrics],
        's3_metrics': [s3_metrics],
        'mwaa_metrics': [mwaa_metrics],
        'redshift_metrics': [redshift_metrics]
    }
    # print(de_metrics_summary)
    return de_metrics_summary


def get_metrics_cursor():
    """
    Get the cursor for the datalake_config database
    :return:
    """
    host = datalake_config_prod_host
    port = datalake_port
    uname = datalake_config_prod_user
    pwd = os.environ['DATALAKE_CONFIG_PROD_PASSWORD']
    db = datalake_db
    conn = mysql.connector.connect(
        host=host,
        user=uname,
        password=pwd,
        database=db,
        port=port
    )
    return conn


def insert_aws_cost_metrics(service_cost_dict, total_cost, run_date, environment):
    """
    Inserts AWS cost metrics into the 'de-metrics' MySQL table.

    Args:
        service_cost_dict (dict): The dictionary containing AWS service costs (e.g., {'S3($)': 8.42}).
        run_date (str): The date of the metric run.
        environment (str): The environment for the metrics ('prod' or 'stage').
    """
    conn = None
    cur = None
    try:
        conn = get_metrics_cursor()
        cur = conn.cursor()
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        metrics_to_insert = []

        for service_name_with_unit, cost in service_cost_dict.items():
            metric_name = 'cost'
            service_name_cleaned = re.sub(r'[^\w\s]', '', service_name_with_unit).strip()
            metrics_to_insert.append((
                run_date, environment, 'aws_cost', service_name_cleaned, metric_name, cost, current_timestamp
            ))

        if total_cost is not None:
            metrics_to_insert.append((
                run_date, environment, 'aws_cost', 'Total Cost', 'total-cost', total_cost, current_timestamp
            ))

        insert_query = """
        INSERT INTO datalake_config.de_metrics(
            run_date, environment, category, service_name, metric_name, metric_value, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cur.executemany(insert_query, metrics_to_insert)
        conn.commit()
        print(
            f"Successfully inserted {len(metrics_to_insert)} AWS cost records for {environment} into `de-metrics` table.")

    except mysql.connector.Error as err:
        print(f"Error inserting AWS cost data into MySQL: {err}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"An unexpected error occurred while inserting AWS cost data: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def insert_metrics_to_mysql(metrics_summary, run_date, environment='prod'):
    """
    Inserts the summarized DE metrics (spark, s3, mwaa, redshift) into the 'de-metrics' MySQL table.

    Args:
        metrics_summary (dict): The dictionary containing spark_metrics, s3_metrics, mwaa_metrics, and redshift_metrics.
        run_date (str): The date of the metric run (e.g., '2025-10-18').
        environment (str): The environment for the metrics (e.g., 'prod').
    """
    conn = None
    cur = None
    try:
        conn = get_metrics_cursor()
        cur = conn.cursor()
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        metrics_to_insert = []

        for category, metrics_list in metrics_summary.items():
            service_map = {
                'spark_metrics': 'spark',
                's3_metrics': 's3-metrics',
                'mwaa_metrics': 'mwaa',
                'redshift_metrics': 'redshift-metrics'
            }

            service_name = service_map.get(category, 'Other')
            category_name = category.split('_')[0]

            if metrics_list and isinstance(metrics_list[0], dict):
                metrics_dict = metrics_list[0]
                for key, value in metrics_dict.items():
                    standard_metric_name = key.split(' ', 1)[1] if key[0].isdigit() and ' ' in key else key

                    metrics_to_insert.append((
                        run_date, environment, category_name, service_name, standard_metric_name, value,
                        current_timestamp
                    ))

        insert_query = """
        INSERT INTO datalake_config.de_metrics (
            run_date, environment, category, service_name, metric_name, metric_value, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cur.executemany(insert_query, metrics_to_insert)
        conn.commit()
        print(f"\nSuccessfully inserted {len(metrics_to_insert)} DE metrics records into `de-metrics` table.")

    except mysql.connector.Error as err:
        print(f"Error inserting DE data into MySQL: {err}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"An unexpected error occurred while inserting DE data: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def insert_cluster_metrics(cluster_summary, run_date, cluster_type, environment='prod'):
    """
    Inserts S3 or Redshift cluster metrics into the `de_metrics` MySQL table.

    Args:
        cluster_summary (dict): Dictionary returned by `get_s3_metrics_summary` or `get_redshift_metrics_summary`.
        run_date (str): Run date of the metrics (e.g., '2025-10-23').
        cluster_type (str): Type of cluster ('s3' or 'redshift').
        environment (str): Environment name ('prod', 'stage', etc.).
    """
    if cluster_type not in ['s3', 'redshift']:
        raise ValueError("cluster_type must be either 's3' or 'redshift'")

    conn = None
    cur = None
    try:
        conn = get_metrics_cursor()
        cur = conn.cursor()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        metrics_to_insert = []
        for metric_name, metric_value in cluster_summary.items():
            metrics_to_insert.append((
                run_date,
                environment,
                f"{cluster_type}_cluster",
                cluster_type,
                metric_name,
                metric_value,
                timestamp
            ))

        insert_query = """
        INSERT INTO datalake_config.de_metrics (
            run_date, environment, category, service_name, metric_name, metric_value, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cur.executemany(insert_query, metrics_to_insert)
        conn.commit()
        print(f"Inserted {len(metrics_to_insert)} {cluster_type.upper()} cluster metrics into `de_metrics` table.")

    except mysql.connector.Error as err:
        print(f"MySQL error inserting {cluster_type.upper()} cluster metrics: {err}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"Unexpected error inserting {cluster_type.upper()} cluster metrics: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def main():
    start_time_iso, end_time_iso = datetime_iso()
    start_time = start_time_iso.split("T")[0]
    end_time = end_time_iso.split("T")[0]
    run_date = end_time

    print(f"\nCalculating metrics for the time period: {start_time} to {end_time}\n")

    service_cost_dict_prod, total_cost_prod = get_datalake_cost(start_time, end_time, env='prod')
    print("----------------Total Cost for Prod Environment----------------\n", total_cost_prod, "\n")
    final_service_cost_prod_dict = {key_dict.get(k, k): v for k, v in service_cost_dict_prod.items()}
    print("----------------Service Cost for Prod Environment----------------")
    for key, value in final_service_cost_prod_dict.items():
        print(key, ":", value)

    service_cost_dict_stage, total_cost_stage = get_datalake_cost(start_time, end_time, env='stage')
    print("---Total Cost for Stage Environment---\n", total_cost_stage, "\n")
    print("---Service Cost for Stage Environment---")
    final_service_cost_stage_dict = {key_dict.get(k, k): v for k, v in service_cost_dict_stage.items()}
    for key, value in final_service_cost_stage_dict.items():
        print(key, ":", value)

    insert_aws_cost_metrics(final_service_cost_prod_dict, total_cost_prod, run_date, environment='prod')
    insert_aws_cost_metrics(final_service_cost_stage_dict, total_cost_stage, run_date, environment='stage')

    s3_summary = get_s3_metrics_summary(start_time=start_time, end_time=end_time)
    print("----------------S3 cluster Metrics----------------\n")
    for key, value in s3_summary.items():
        print(key, ":", value)

    insert_cluster_metrics(s3_summary, run_date, cluster_type='s3', environment='prod')

    redshift_summary = get_redshift_metrics_summary(start_time=start_time, end_time=end_time)
    print("----------------Redshift cluster Metrics----------------\n")
    for key, value in redshift_summary.items():
        print(key, ":", value)

    insert_cluster_metrics(redshift_summary, run_date, cluster_type='redshift', environment='prod')

    de_metrics_summary = get_de_metrics(start_time, end_time, s3_summary, redshift_summary)
    print("----------------Data Engineering Metrics----------------\n")
    for key, value in de_metrics_summary.items():
        print("\n", str(key).upper(), "\n")
        for k, v in value[0].items():
            print(k, ":", v)

    insert_metrics_to_mysql(de_metrics_summary, run_date, environment='prod')

if __name__ == '__main__':
    main()
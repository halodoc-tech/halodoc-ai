import csv
import logging
import os
import time
import boto3
import requests

from utils.alert_notification import *
from utils.variables import *
from datetime import datetime, timezone, timedelta


unhealthy_component = []

HEALTH_CSV = os.environ.get("HEALTH_CSV_PATH", "airflow_health.csv")


def write_health_snapshot(component_status):
    """Append the current component health to a CSV (timestamp, component, status)."""
    is_new = not os.path.exists(HEALTH_CSV)
    ts = datetime.now(timezone.utc).isoformat()
    with open(HEALTH_CSV, "a", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(["timestamp_utc", "component", "status"])
        for component, status in component_status.items():
            writer.writerow([ts, component, status])


def create_web_token():
    aws_region = region
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.getenv('AWS_SESSION_TOKEN')
    mwaa = boto3.client('mwaa', region_name=aws_region, aws_access_key_id=aws_access_key_id,
                        aws_secret_access_key=aws_secret_access_key, aws_session_token=aws_session_token)
    env = os.getenv('Environment')
    if env == 'stage':
        airflow_env_name = stage_airflow_env_name
    elif env == 'prod':
        airflow_env_name = prod_airflow_env_name
    else:
        raise Exception("Invalid environment")
    response = mwaa.create_web_login_token(Name=airflow_env_name)
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        print(response)
        webServerHostName = response["WebServerHostname"]
        webToken = response["WebToken"]
        airflowUIUrl = 'https://{0}/pluginsv2/aws_mwaa/aws-console-sso?login=true#{1}'.format(
            webServerHostName, webToken
        )
        print("Here is your Airflow UI URL: ")
        print(airflowUIUrl)
        return response
    else:
        raise Exception("unable to create web login token")


def get_session_info():
    """
    Retrieves the web server hostname and JWT token for an MWAA3 environment.

    Returns:
        tuple: A tuple containing the web server hostname and JWT token, or raises on failure.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        try:
            response = create_web_token()
        except Exception as err:
            raise Exception(f"Failed to create web login token: {err}")

        web_server_host_name = response["WebServerHostname"]
        web_token = response["WebToken"]

        login_url = f"https://{web_server_host_name}/pluginsv2/aws_mwaa/login"
        login_payload = {"token": web_token}

        try:
            response = requests.post(login_url, data=login_payload, timeout=10)
        except Exception as err:
            print("unable to login", err)

        if response.status_code == 200:
            print("Logged in successfully")
            jwt_token = response.cookies["_token"]
            print("JWT Token", jwt_token)
            return web_server_host_name, jwt_token
        else:
            raise Exception(f"Failed to log in: HTTP {response.status_code}")
    except requests.RequestException as e:
        raise Exception(f"UnExpected error - : {e}")


def checkInstanceHealth():
    unhealthy_component = []
    try:
        web_server_host_name, jwt_token = get_session_info()
        if not jwt_token:
            raise Exception("JWT token not found")
    except Exception as e:
        raise Exception(f"Request failed: {e}")

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }

    url = f"https://{web_server_host_name}/api/v2/monitor/health"

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        components['Metadatabase'] = response.json()['metadatabase']['status']
        components['Scheduler'] = response.json()['scheduler']['status']
        components['Triggerer'] = response.json()['triggerer']['status']
        components['Dagprocessor'] = response.json()['dag_processor']['status']
        print("Checking Airflow Instance Health")
        print(components)
        for key, value in components.items():
            if value != 'healthy':
                unhealthy_component.append(key)
        return unhealthy_component
    else:
        raise Exception("Airflow Instance Health Check failed due to status code: ", response.status_code)


def checkImportErrors():
    try:
        web_server_host_name, jwt_token = get_session_info()
        if not jwt_token:
            raise Exception("JWT token not found")
    except Exception as e:
        raise Exception(f"Request failed: {e}")

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }

    error_dags = []
    url = f"https://{web_server_host_name}/api/v2/importErrors"

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        if response.json()['total_entries'] == 0:
            print("No import errors found")
            return 0, error_dags
        else:
            print("Found import errors")
            print(response.json())

            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

            for error in response.json()['import_errors']:
                # Parse the timestamp from the error (e.g. "2026-03-06T05:13:26+00:00")
                error_timestamp = datetime.fromisoformat(error['timestamp'])
                if error_timestamp < one_hour_ago:
                    print(f"Skipping old import error (older than 1 hour): {error['filename']}")
                    continue

                dag_path = error['filename']
                dag_name = dag_path.split('/')[-1].split('.')[0]
                error_dags.append(dag_name)

            recent_error_count = len(error_dags)
            if recent_error_count == 0:
                print("No recent import errors found within the last hour")
            return recent_error_count, error_dags
    else:
        raise Exception(f"Failed to get import errors: HTTP {response.status_code} - {response.text}")


def main():
    unhealthy_component = checkInstanceHealth()
    if unhealthy_component:
        time.sleep(150)
        unhealthy_component = checkInstanceHealth()
        if unhealthy_component:
            time.sleep(150)
            unhealthy_component = checkInstanceHealth()
            if unhealthy_component:
                print("Airflow Instance is not healthy.Sending Alert...")
                print(unhealthy_component)
                MESSAGE = f":monit-alert:The following Airflow Component is down. Please check the logs for more information.:monit-alert:\n```{unhealthy_component}```"
                send_alert(MESSAGE)
            else:
                print("Airflow Instance became healthy within a minute")
        else:
            print("Airflow Instance is healthy")
    else:
        print("Airflow Instance is healthy")

    write_health_snapshot(components)

    error_count, error_dags = checkImportErrors()
    if error_count > 0:
        print("Import Errors found. Retrying after a minute...")
        time.sleep(60)
        error_count, error_dags = checkImportErrors()
        if error_count > 0:
            print("Total Import Errors: ", error_count)
            print("Dags with Import Errors: ")
            print(error_dags)
            MESSAGE = f":monit-alert:{error_count} DAG Import Error found in airflow:monit-alert:\n```{error_dags}```"
            send_gchat_alert(MESSAGE)
        else:
            print("Import Errors resolved within a minute")
    else:
        print("No Import Errors found")


if __name__ == '__main__':
    main()
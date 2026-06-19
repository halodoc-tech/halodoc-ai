import logging
import os
import sys
import time

import boto3
import requests
from datetime import datetime, timezone

from utils.variables import *

logger = logging.getLogger(__name__)


def trigger_dag(env, dag_id, region, sheet_range):
    """
    Triggers a DAG in a specified MWAA environment using the Airflow REST API.

    Args:
        env (str): stage/prod environment.
        dag_id (str): Name of the DAG to trigger.
        region (str): AWS region where the MWAA environment is hosted.
        sheet_range (str): Sheet range to pass as DAG config.
    """
    if env == 'stage':
        env_name = stage_airflow_env_name
    elif env == 'prod':
        env_name = prod_airflow_env_name
    else:
        sys.exit(f"Wrong env - {env}")

    logger.info("Attempting to trigger DAG %s in environment %s at region %s", dag_id, env_name, region)

    try:
        web_server_host_name, jwt_token = get_session_info(region, env_name)
        if not jwt_token:
            raise Exception("Authentication failed, no JWT token retrieved.")
    except Exception as e:
        raise Exception(f"Failed to get session info: {e}")

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    json_body = {
        "logical_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "conf": {"sheet_range": sheet_range},
    }
    url = f"https://{web_server_host_name}/api/v2/dags/{dag_id}/dagRuns"

    post_trigger_dag(headers, dag_id, json_body, url, web_server_host_name)


def post_trigger_dag(headers, dag_id, json_body, url, web_server_host_name):
    """Send POST request to trigger the DAG and poll until completion."""
    try:
        response = requests.post(url, headers=headers, json=json_body)

        if response.status_code == 200:
            logger.info("DAG triggered successfully.")
            dag_run_id = response.json()["dag_run_id"]
            status_url = f"https://{web_server_host_name}/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}"

            start_time = time.time()
            timeout_duration = 300
            status = None

            while status != "success":
                if time.time() - start_time > timeout_duration:
                    raise Exception("DAG run timed out.")

                response = requests.get(status_url, headers=headers, timeout=10)
                if response.status_code != 200:
                    raise Exception(f"Failed to get DAG status: HTTP {response.status_code} - {response.text}")

                status = response.json().get("state")
                logger.info("DAG status: %s", status)

                if status == "failed":
                    raise Exception("DAG failed.")

                time.sleep(15)

            logger.info("DAG completed successfully.")
        else:
            raise Exception(f"Failed to trigger DAG: HTTP {response.status_code} - {response.text}")

    except requests.RequestException as e:
        raise Exception(f"Failed to trigger DAG: {e}")


def create_web_token(env_name, region):
    """Create an MWAA web login token using boto3."""
    logger.info("Creating web token for env: %s", env_name)
    mwaa = boto3.client(
        "mwaa",
        region_name=region,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    )
    try:
        response = mwaa.create_web_login_token(Name=env_name)
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            return response
        else:
            raise Exception("Response not received successfully")
    except Exception as err:
        raise Exception(f"Failed to create web login token: {err}")


def get_session_info(region, env_name):
    """
    Retrieves the web server hostname and JWT token for an MWAA3 environment.

    Args:
        region (str): The AWS region where the MWAA environment is located.
        env_name (str): The name of the MWAA environment.

    Returns:
        tuple: (web_server_host_name, jwt_token) or raises on failure.
    """
    logger.info("Getting session info")
    try:
        response = create_web_token(env_name, region)
    except Exception as err:
        raise Exception(f"Failed to create web login token: {err}")

    web_server_host_name = response["WebServerHostname"]
    web_token = response["WebToken"]

    login_url = f"https://{web_server_host_name}/pluginsv2/aws_mwaa/login"
    login_payload = {"token": web_token}

    try:
        response = requests.post(login_url, data=login_payload, timeout=10)
    except Exception as err:
        raise Exception(f"Failed to login: {err}")

    if response.status_code == 200:
        logger.info("Logged in successfully")
        jwt_token = response.cookies["_token"]
        return web_server_host_name, jwt_token
    else:
        raise Exception(f"Failed to log in: HTTP {response.status_code}")
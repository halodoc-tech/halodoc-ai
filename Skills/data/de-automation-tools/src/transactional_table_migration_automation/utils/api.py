import os
import sys

import boto3
import requests
from utils.variables import *
import logging
import time
from datetime import datetime, timezone



def wait_for_task_status(dms_client, replication_task_arn, wait_status, max_retries=10, wait_time=10):
    attempt = 1
    accepted_status = ["deleted", "ready", "running", "stopped", "load_complete"]
    if wait_status not in accepted_status:
        sys.exit("not recognize status, status: {wait_status} "
                 "accepted_status: {accepted_status}"
                 .format(wait_status=wait_status, accepted_status=accepted_status))
    logging.info(f"waiting for the replication task to reach {wait_status} state")
    status = None
    while attempt <= max_retries and status != wait_status:
        response = dms_client.describe_replication_tasks(
            Filters=[
                {
                    "Name": "replication-task-arn",
                    "Values": [
                        replication_task_arn,
                    ],
                },
            ]
        )
        status = response['ReplicationTasks'][0]['Status']
        print(f"status: {status} attempt: {attempt}")
        if status == "failed":
            err = f'''replication task failed during {wait_status}'''
            raise Exception(err)
        time.sleep(wait_time)
        attempt += 1


def wait_for_instance_status(dms_client, replication_instance_arn, wait_status, max_retries=60, wait_time=30):
    attempt = 1
    accepted_status = ["available", "modifying", "rebooting", "failed", "storage-full"]
    if wait_status not in accepted_status:
        sys.exit("not recognize status, status: {wait_status}"
                 " accepted_status: {accepted_status}"
                 .format(wait_status=wait_status, accepted_status=accepted_status))
    logging.info(f"waiting for the replication task to reach {wait_status} state")
    time.sleep(wait_time)
    status = None
    while attempt <= max_retries and status != wait_status:
        response = dms_client.describe_replication_instances(
            Filters=[
                {
                    "Name": "replication-instance-arn",
                    "Values": [
                        replication_instance_arn,
                    ],
                },
            ]
        )
        status = response['ReplicationInstances'][0]['ReplicationInstanceStatus']
        logging.info(f"status: {status} attempt: {attempt}")
        if status == "failed":
            raise Exception(f'''replication task failed during {wait_status}''')
        time.sleep(wait_time)
        attempt += 1


def resize_replication_instance(env, dms_client, scale):
    if env == 'stage':
        print("Scaling up not required for the replication instance in stage")
        return
    if scale == 'up':
        replication_instance_class = upscale_instance_class
    elif scale == 'down':
        replication_instance_class = down_instance_class
    else:
        sys.exit(f"Wrong scale -{scale}".format(scale=scale))
    if env == 'prod':
        task_arn = prod_full_load_replication_instance_arn
    else:
        sys.exit(f"Wrong env -{env}".format(env=env))
    print("Resizing replication instance")
    print("Modifying the replication instance")
    response = dms_client.modify_replication_instance(
        ReplicationInstanceArn=task_arn,
        ApplyImmediately=True,
        ReplicationInstanceClass=replication_instance_class,
    )
    if scale == 'up':
        print("Waiting for replication instance to be modified")
        wait_for_instance_status(
            dms_client=dms_client,
            replication_instance_arn=task_arn, wait_status="available"
        )
        print("Waited till replication instance modifying")
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            print('Replication instance modified successfully.', response)
            print("Replication instance is scaled up")
            return response
        else:
            print('Error modifying replication instance:{response}'
                  .format(response=response))


def modify_replication_task(dms_client, replication_task_arn, new_table_mappings, migration_type):
    modify_response = dms_client.modify_replication_task(
        ReplicationTaskArn=replication_task_arn,
        MigrationType=migration_type,
        TableMappings=new_table_mappings
    )
    print("Modifying the replication task")
    wait_for_task_status(
        dms_client=dms_client,
        replication_task_arn=replication_task_arn, wait_status="stopped"
    )
    print("Waited till modify_task modifying")

    if modify_response['ResponseMetadata']['HTTPStatusCode'] == 200:
        print('Replication task modified successfully.', modify_response)
        return modify_response
    else:
        print('Error modifying replication task:{modify_response}'
              .format(modify_response=modify_response))


def restart_replication_task(dms_client, replication_task_arn):
    describe_response = dms_client.describe_replication_tasks(
        Filters=[
            {
                'Name': 'replication-task-arn',
                'Values': [
                    replication_task_arn,
                ]
            },
        ],
        MaxRecords=100,
        Marker='string',
        WithoutSettings=True
    )
    status = describe_response['ReplicationTasks'][0]['Status']
    if status == 'ready':
        replication_type = 'start-replication'
    else:
        replication_type = 'reload-target'
    restart_response = dms_client.start_replication_task(
        ReplicationTaskArn=replication_task_arn,
        StartReplicationTaskType=replication_type
    )
    print("Restarting the replication task")
    wait_for_task_status(
        dms_client=dms_client,
        replication_task_arn=replication_task_arn, wait_status="running"
    )
    print("Waited till restart_task running")
    wait_for_task_status(
        dms_client=dms_client,
        replication_task_arn=replication_task_arn, wait_status="stopped"
    )
    if restart_response['ResponseMetadata']['HTTPStatusCode'] == 200:
        print('Replication task restarted successfully.', restart_response)
        return restart_response
    else:
        print('Error modifying replication task:{restart_response}'
              .format(restart_response=restart_response))


def describe_replication_task(dms_client, replication_task_name):
    describe_response = dms_client.describe_replication_tasks(
        Filters=[
            {
                'Name': 'replication-task-id',
                'Values': [
                    replication_task_name,
                ]
            },
        ],
        MaxRecords=100,
        WithoutSettings=False
    )
    if describe_response['ResponseMetadata']['HTTPStatusCode'] == 200:
        return describe_response
    else:
        print('Error modifying replication task:{describe_response}'
              .format(describe_response=describe_response))


def trigger_full_load_dag(env, dag_id, region):
    """
    Triggers a DAG in a specified MWAA environment using the Airflow REST API.

    Args:
        env (str): stage/prod environment.
        dag_id (str): Name of the DAG to trigger.
        region (str): AWS region where the MWAA environment is hosted.
    """
    if os.environ.get('TEST_RUN') == 'True':
        return
    if env == 'stage':
        env_name = stage_airflow_env_name
    elif env == 'prod':
        env_name = prod_airflow_env_name
    else:
        sys.exit("Wrong env -", env)

    print(f"Attempting to trigger DAG {dag_id} in environment {env_name} at region {region}")

    try:
        web_server_host_name, jwt_token = get_session_info(region, env_name)
        if not jwt_token:
            logging.error("Authentication failed, no JWT token retrieved.")
            return
    except Exception as e:
        logging.error(f"Error retrieving session info: {str(e)}")
        return

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    json_body = {
        "conf": {},
        "logical_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",

    }


    url = f"https://{web_server_host_name}/api/v2/dags/{dag_id}/dagRuns"

    response = requests.post(url, headers=headers, json=json_body)
    if response.status_code == 200:
        logging.info("DAG triggered successfully.")
    else:
        logging.error(f"Failed to trigger DAG: HTTP {response.status_code} - {response.text}")
    return response


def create_mwaa_client(region: str):
    mwaa = boto3.client(
        'mwaa',
        region_name=region,
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        aws_session_token=os.getenv('AWS_SESSION_TOKEN')
    )
    return mwaa


def create_web_token(env_name, mwaa_client):
    print("Creating web token")
    try:
        response = mwaa_client.create_web_login_token(Name=env_name)
        print(response)
        webServerHostName = response["WebServerHostname"]
        webToken = response["WebToken"]
        airflowUIUrl = 'https://{0}/pluginsv2/aws_mwaa/aws-console-sso?login=true#{1}'.format(
            webServerHostName, webToken
        )
        print("Here is your Airflow UI URL: ")
        print(airflowUIUrl)
        return response
    except Exception as err:
        print("unable to create web login token", err)


def get_session_info(region, env_name):
    """
    Retrieves the web server hostname and JWT token for an MWAA3 environment.

    Args:
        region (str): The AWS region where the MWAA environment is located.
        env_name (str): The name of the MWAA environment.

    Returns:
        tuple: (web_server_host_name, jwt_token) or (None, None) on failure.
    """
    print("Getting session info")
    try:
        try:
            mwaa_client = create_mwaa_client(region)
            response = create_web_token(env_name, mwaa_client)
        except Exception as err:
            logging.error("Failed to create web login token: %s", str(err))
            return None

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
            return web_server_host_name, jwt_token
        else:
            logging.error("Failed to log in: HTTP %d", response.status_code)
            return None
    except requests.RequestException as e:
        logging.error("Request failed: %s", str(e))
        return None
    except Exception as e:
        logging.error("An unexpected error occurred: %s", str(e))
        return None
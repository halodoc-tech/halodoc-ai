import os

import mysql.connector
import boto3

from configs.datalake_config_creds import *
from sql_scripts.gsheet_export import *
from utils.api import trigger_dag
from utils.variables import *


def get_crawler_data_sources(glue, crawler_name):
    try:
        response = glue.get_crawler(Name=crawler_name)
        return response['Crawler']['Targets']['S3Targets']
    except Exception as e:
        raise Exception(f"Failed to get the crawler data sources - {e}")


def update_crawler(glue, new_s3_targets, crawler_name):
    try:
        response = glue.update_crawler(
            Name=crawler_name,
            Targets={
                'S3Targets': new_s3_targets
            }
        )
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            print(response)
            print("Updated the crawler successfully")
        else:
            raise Exception(f"Response not received successfully")
    except Exception as e:
        raise Exception(f"Failed to update the crawler - {e}")


def run_crawler(glue, crawler_name):
    try:
        response = glue.start_crawler(Name=crawler_name)
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            print(response)
            print("Crawler started successfully")
        else:
            raise Exception(f"Response not received successfully")
    except Exception as e:
        raise Exception(f"Failed to start the crawler - {e}")


def gsheet_validator(cursor, sheet_range, sheet_id):
    validation_query = '''
    Select sheet_range from datalake_config.gsheet_export where sheet_range LIKE '{sheet_range}%' and sheet_id = '{sheet_id}';
    '''.format(sheet_range=sheet_range.split('!')[0], sheet_id=sheet_id)
    cursor.execute(validation_query)
    if cursor.fetchone():
        print("Sheet already present in the table")
        return 1
    else:
        return 0


def prepare_connection_parameters(env):
    if env == 'stage':
        config_host = DATALAKE_CONFIG_STAGE_HOST
        config_username = DATALAKE_CONFIG_STAGE_USER
        config_pass = os.getenv('DATALAKE_CONFIG_STAGE_PASSWORD')

    elif env == 'prod':
        config_host = DATALAKE_CONFIG_PROD_HOST
        config_username = DATALAKE_CONFIG_PROD_USER
        config_pass = os.getenv('DATALAKE_CONFIG_PROD_PASSWORD')
    else:
        raise Exception("Invalid environment")
    return config_host, config_username, config_pass


def create_database_connection(host, username, password, env):
    print(f"Connecting to datalake-config-{env} database")
    try:
        return mysql.connector.connect(
            host=host,
            user=username,
            password=password
        )
    except Exception as e:
        raise Exception("Failed to connect to the database")


def handle_new_table(cursor, sheet_id, sheet_range, new_table_name, job_group, business_unit, env):
    if gsheet_validator(cursor, sheet_range, sheet_id) == 0:
        query = build_insert_query(new_table_name, sheet_id, sheet_range, job_group, business_unit, env)
        execute_query(cursor, query)
    else:
        print("This Sheet is already present - ", "sheet_range.split('!')[0]")
        print("Following the next step, Triggering the DAG")


def handle_new_column(cursor, sheet_id, sheet_range):
    if gsheet_validator(cursor, sheet_range, sheet_id) == 1:
        query = build_update_query(sheet_range, sheet_id)
        execute_query(cursor, query)
    else:
        raise ValueError("Sheet not present in the table: " + sheet_range.split('!')[0])


def build_insert_query(new_table_name, sheet_id, sheet_range, job_group, business_unit, env):
    return INSERT_INTO_GSHEET_EXPORT.format(
        new_table_name=new_table_name,
        sheet_id=sheet_id,
        sheet_range=sheet_range,
        job_group=job_group,
        business_unit=business_unit,
        env=env,
        bucket_prefix=datalake_bucket_prefix
    )


def build_update_query(sheet_range, sheet_id):
    return UPDATE_GSHEET_EXPORT.format(
        sheet_range=sheet_range,
        sheet_id=sheet_id,
        tgt_sheet_name=sheet_range.split('!')[0]
    )


def execute_query(cursor, query):
    print(f"Executing query: {query}")
    cursor.execute(query)


def insert_to_gsheet_export(env, new_table_name, sheet_id, sheet_range, job_group, business_unit, execution_method):
    config_host, config_username, config_pass = prepare_connection_parameters(env)
    job_group = str(job_group).split(',')[0]
    business_unit = str(business_unit).split(',')[0]
    try:
        connection = create_database_connection(config_host, config_username, config_pass, env)
        cursor = connection.cursor()

        if execution_method == 'new-table':
            handle_new_table(cursor, sheet_id, sheet_range, new_table_name, job_group, business_unit, env)
        elif execution_method == 'new-column':
            handle_new_column(cursor, sheet_id, sheet_range)
        else:
            raise Exception("Invalid execution method")
        connection.commit()
    except Exception as e:
        raise Exception("Failed to insert into datalake_config.gsheet_export", e)
    finally:
        cursor.close()
        connection.close()


def get_env_variables():
    aws_region = 'ap-southeast-1'
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.getenv('AWS_SESSION_TOKEN')
    env = os.getenv('Environment')
    new_table_name = os.getenv('GSHEET_TABLE_NAME')
    sheet_id = os.getenv('GSHEET_ID')
    sheet_range = os.getenv('SHEET_RANGE')
    job_group = os.getenv('JOB_GROUP')
    business_unit = os.getenv('BUSINESS_UNIT')
    execution_method = os.getenv('ExecutionMethod')

    return aws_region, aws_access_key_id, aws_secret_access_key, aws_session_token, env, new_table_name, sheet_id, sheet_range, job_group, business_unit, execution_method


def input_validation(execution_method, env, new_table_name, sheet_id, sheet_range, job_group, business_unit):
    if execution_method == 'new-table':
        if env is None or new_table_name is None or sheet_id is None or sheet_range is None or job_group is None or business_unit is None:
            raise Exception("Invalid input parameters. Please check")
    elif execution_method == 'new-column':
        if sheet_range is None or len(sheet_range.split('!')) != 2 or sheet_id is None:
            raise Exception("Invalid input parameters. Please check")
    else:
        raise Exception("Invalid execution method. Please check")
    print(
        f"Environment - {env} Table Name - {new_table_name} Sheet ID - {sheet_id} Sheet Range - {sheet_range} Job Group - {job_group} Business Unit - {business_unit}"
    )


def assign_values(env, new_table_name, sheet_range, job_group):
    if new_table_name:
        new_table_name = new_table_name.split(',')[0]
    tgt_sheet_name = str(sheet_range).split('!')[0]
    job_group = str(job_group).split(',')[0]
    # if job_group not in ('g0', 'g1'):
    #     raise Exception("Invalid job group")
    if env == 'stage':
        crawler_name = stage_crawler_name
    elif env == 'prod':
        crawler_name = prod_crawler_name
    else:
        raise Exception("Invalid environment")
    new_path = f's3://{datalake_bucket_prefix}-{env}/raw/fileupload/source=gsheet/parquet/{tgt_sheet_name}/'

    return new_table_name, tgt_sheet_name, dag_name, crawler_name, new_path


def main():
    # parameters

    aws_region, aws_access_key_id, aws_secret_access_key, aws_session_token, env, new_table_name, sheet_id, sheet_range, job_group, business_unit, execution_method = get_env_variables()

    # Input validation
    input_validation(execution_method, env, new_table_name, sheet_id, sheet_range, job_group, business_unit)

    new_table_name, tgt_sheet_name, dag_name, crawler_name, new_path = assign_values(env,
                                                                                     new_table_name,
                                                                                     sheet_range, job_group
                                                                                     )

    if execution_method == 'new-table':
        insert_to_gsheet_export(env=env, new_table_name=new_table_name, sheet_id=sheet_id, sheet_range=sheet_range,
                                job_group=job_group,
                                business_unit=business_unit, execution_method=execution_method)
    elif execution_method == 'new-column':
        print("Updating sheet range in gsheet export")
        insert_to_gsheet_export(env=env, new_table_name=None, sheet_id=sheet_id, sheet_range=sheet_range,
                                job_group=None,
                                business_unit=None, execution_method=execution_method)
    trigger_dag(env, dag_name, aws_region, sheet_range)
    glue = boto3.client('glue', region_name=aws_region, aws_access_key_id=aws_access_key_id,
                        aws_secret_access_key=aws_secret_access_key, aws_session_token=aws_session_token)
    if execution_method == 'new-table':
        current_s3_targets = get_crawler_data_sources(glue, crawler_name)
        data_source_name = '/{data_source_name}/'.format(data_source_name=sheet_range.split('!')[0])
        if data_source_name not in str(current_s3_targets):
            print("Adding sheet to the crawler data sources")
            temp_s3_target = {**current_s3_targets[0], 'Path': new_path}
            current_s3_targets.append(temp_s3_target)
            new_s3_targets = current_s3_targets
            print("New S3 target = ", new_s3_targets)
            update_crawler(glue, new_s3_targets, crawler_name)
        else:
            print("Sheet already present in the crawler data sources, Kindly check")
            print(current_s3_targets)
    print("Running the crawler")
    run_crawler(glue, crawler_name)


if __name__ == '__main__':
    main()

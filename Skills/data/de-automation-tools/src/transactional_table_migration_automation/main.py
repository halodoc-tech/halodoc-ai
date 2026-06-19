import json
import os
import boto3
import mysql.connector
import requests
import sys
import time
from sql_scripts.datalake_config import *
from configs.datalake_config_creds import *
from utils.variables import *
from utils.api import *


def connect_mysql_db(rds_creds):
    conn = mysql.connector.connect(
        host=rds_creds["host"],
        user=rds_creds["user"],
        password=rds_creds["password"],
        port=rds_creds["port"]
    )
    return conn


def get_table_list(schema, rds_creds):
    query_str = ("select distinct table_name from INFORMATION_SCHEMA.columns"
                 " where table_schema = '{0}' and table_name not like "
                 "'%DATABASE%' and table_name not like '%Database%' and"
                 " table_name not like '%Clean%' and table_name not "
                 "like '%Duplicate%';").format(schema)
    conn = connect_mysql_db(rds_creds)
    mycur = conn.cursor()
    mycur.execute(query_str)
    myresult = mycur.fetchall()
    conn.close()
    return myresult


def map_data_type(datatype):  # Remove once schema definition is added to master table
    if datatype == "character varying":
        return "varchar"
    elif datatype == "numeric":
        return "integer"
    elif datatype == "bigint":
        return "long"
    elif datatype == "longtext":
        return "string"
    elif datatype == "datetime":
        return "timestamp"
    elif datatype == "tinyint":
        return "integer"
    elif datatype == "double":
        return "double"
    elif datatype == "text":
        return "string"
    elif datatype == "timestamp":
        return "timestamp"
    elif datatype == "json":
        return "string"
    elif datatype == "float":
        return "float"
    elif datatype == "mediumtext":
        return "string"
    elif datatype == "char":
        return "string"
    elif datatype == "date":
        return "date"
    elif datatype == "time":
        return "string"
    elif datatype == "smallint":
        return "short"
    elif datatype == "bit":
        return "boolean"
    elif datatype == "int":
        return "integer"
    elif "decimal" in datatype:
        # print(datatype)
        return datatype
    else:
        return "string"


def create_query(env, execution_method, schema_name, src_db_name, tgt_dbname, table_list, result_rds_endpoints,
                 partition_column, incr_key, job_group, frequency_in_mins):
    values = []
    watermark_values = []
    updt_sqs = []
    rds_creds = {'host': result_rds_endpoints[0][1], 'port': result_rds_endpoints[0][2],
                 'user': result_rds_endpoints[0][3],
                 'password':
                     get_vault_key(result_rds_endpoints[0][4], env)['DB_PASSWORD']}

    for table_name in table_list:
        watermark_val = (schema_name, table_name)
        watermark_values.append(watermark_val)
        conn = connect_mysql_db(rds_creds)
        mycur = conn.cursor()
        schema_def_query = SCHEMA_DEF_QUERY.format(schema_name, table_name)
        mycur.execute(schema_def_query)
        myresult = mycur.fetchall()
        schema_doc = {"Op": "string"}
        for field in myresult:
            schema_doc[field[0]] = map_data_type(field[1])
        if incr_key not in schema_doc:
            print("Type = ",type(schema_doc))
            schema_doc[incr_key] = "timestamp"
            print("Incremental key not found in schema definition.\nNew schema definition = ", schema_doc)
        schema_doc = json.dumps(schema_doc)
        conn.close()
        value = (
            src_db_name,
            schema_name,
            table_name,
            f"raw/rds-mysql/full-load/{schema_name}/{table_name}/",
            f"processed/rds-mysql/{schema_name}/{table_name}/",
            tgt_dbname,
            schema_name,
            table_name,
            "id",
            "ar_h_change_seq",
            incr_key,
            partition_column,
            "COPY_ON_WRITE",
            "Y",
            f"raw/rds-mysql/incremental-load/{schema_name}/{table_name}/",
            "ready",
            f"{schema_doc}",
            "Y",
            '{"ar_h_change_seq": "string"}',
            "Y",
            '{"ar_h_change_seq": "decimal(38)"}',
            20,
            frequency_in_mins,
            job_group,
            "Y",
            "Y"
        )
        values.append(value)
        print("type of value", type(value))
        print("Single Insert sql for", table_name, ' = ', value)
        if execution_method == 'new-column-without-full-load':
            updt_sq = UPDATE_COLUMN_QUERY.format(schema_name=schema_name, table_name=table_name,
                                                 schema_doc=schema_doc)
        else:
            updt_sq = UPDATE_COLUMN_WITH_STATUS_QUERY.format(schema_name=schema_name, table_name=table_name,
                                                             schema_doc=schema_doc)
        updt_sqs.append(updt_sq)

    res = ",\n".join(str(i) for i in values)
    # result = INSERT_QUERY.format(COLUMN_VALUES=res)
    res_watermark = ",\n".join(str(i) for i in watermark_values)
    result_watermark = INSERT_QUERY_WATERMARK.format(COLUMN_VALUES=res_watermark)
    result = INSERT_QUERY.format(COLUMN_VALUES=res)
    updt_sqs_prnt = "\n".join(str(i) for i in updt_sqs)
    # print(updt_sqs_prnt)
    print("\n")
    print(f"------{schema_name}--------")
    print(result_watermark)
    print("\n")
    print(result)
    print("\n")
    # print('type of update',type(updt_sqs_prnt))
    # print(updt_sqs_prnt)

    if execution_method == 'new-table':
        return result_watermark, result
    elif execution_method in ('new-column-with-full-load', 'new-column-without-full-load'):
        return updt_sqs_prnt

def get_dms_task_from_rds_endpoint(cursor, schema_name):
    """
    Fetches DMS task names from RDS Endpoint table using the schema name.
    Returns: DMS full_load_task name
    """
    query = f"""
    select 
       JSON_EXTRACT(`dms_tasks`, '$.full_load_task') AS full_load_task
    from datalake_config.rds_endpoints
    where 
        schema_name = '{schema_name}';
    """
    print("Executing DMS Task fetching query - ",query)
    try:
        cursor.execute(query)
        result = cursor.fetchone()
        return result[0].replace('"', '')
    except Exception as e:
        print("Error in fetching full load task name",e.__str__())



def sql_generator(execution_method, env, schema_name, src_dbname, tgt_dbname, table_names, result_rds_endpoints,
                  partition_column, incr_key, job_group, frequency_in_mins):
    if execution_method == 'new-table':
        watermark, insert = create_query(env, execution_method, schema_name, src_dbname, tgt_dbname,
                                         table_names, result_rds_endpoints, partition_column, incr_key, job_group,
                                         frequency_in_mins)
        return watermark, insert
    elif execution_method in ('new-column-with-full-load', 'new-column-without-full-load'):
        update = create_query(env, execution_method, schema_name, src_dbname, tgt_dbname,
                              table_names, result_rds_endpoints, partition_column, incr_key, job_group,
                              frequency_in_mins)
        return update


def get_vault_key(vault_key, env):
    global response
    if env == "stage":
        vault_base_url = stage_vault_base_url
        vault_token = os.environ.get("VAULT_STAGE_TOKEN")
    elif env == "prod":
        vault_base_url = prod_vault_base_url
        vault_token = os.environ.get("VAULT_PROD_TOKEN")
    else:
        sys.exit("Wrong env - {env}".format(env=env))
    if vault_token:
        print("Vault token found")
    vault_version = "v1"
    vault_url = (
            vault_base_url + "/" + vault_version + "/kv/data/" + env + "/" + vault_key
    )
    vault_headers = {"Authorization": "Bearer {token}".format(token=vault_token)}
    max_try_rs = 5
    retry_interval = 2
    retried_times = 0
    for attempt in range(1, max_try_rs + 1):
        try:
            response = requests.get(
                url=vault_url, headers=vault_headers, params={}, allow_redirects=True
            )
            if os.environ.get('TEST_RUN') == 'True':
                print("Test run")
            else:
                time.sleep(5)
        except Exception as e:
            print(f"Attempt {attempt} failed: {str(e)}")
            if os.environ.get('TEST_RUN') == 'True':
                print("Test run")
            else:
                time.sleep(retry_interval)
            retried_times = retried_times + 1
            continue
        break

    if retried_times == max_try_rs:
        print(f"Failed after {max_try_rs} attempts")
        return None

    response_object = {"status_code": response.status_code, "data": response.content}

    return json.loads(response_object["data"])["data"]["data"]


def execute_query(cursor, query):
    try:
        cursor.execute(query)
    except Exception as e:
        print(e.__str__())


def column_validator(cursor, schema_name, table_names, rds_creds):
    """
    For add-column execution methods: checks whether all columns currently in the source MySQL table
    are already tracked in transformation_master (tgt_schema_definition).
    If every column already exists → raises an error so the entire pipeline is skipped.
    Returns a list of tables that have genuinely new columns to process.
    """
    tables_with_new_columns = []
    for table_name in table_names:
        # fetch current columns tracked in transformation_master for this table
        cursor.execute(
            "SELECT tgt_schema_definition FROM datalake_config.transformation_master "
            "WHERE src_schemaname = '{schema}' AND src_tablename = '{table}';".format(
                schema=schema_name, table=table_name
            )
        )
        row = cursor.fetchone()
        if not row:
            print(f"Table {table_name} not found in transformation_master, skipping column check.")
            tables_with_new_columns.append(table_name)
            continue

        existing_schema = json.loads(row[0])
        existing_columns = set(existing_schema.keys())

        # fetch current columns from source MySQL
        conn = connect_mysql_db(rds_creds)
        mycur = conn.cursor()
        mycur.execute(SCHEMA_DEF_QUERY.format(schema_name, table_name))
        source_columns = {field[0] for field in mycur.fetchall()}
        conn.close()

        new_columns = source_columns - existing_columns
        if not new_columns:
            print(f"All columns in '{table_name}' already exist in transformation_master. No new columns to add.")
        else:
            print(f"Table '{table_name}' has new columns to add: {sorted(new_columns)}")
            tables_with_new_columns.append(table_name)

    return tables_with_new_columns


def table_validator(cursor, schema_name, table_names):
    temp_table_list = []
    for table in table_names:
        query = ("Select etl_id from datalake_config.transformation_master"
                 " where src_schemaname = '{SCHEMA}' and src_tablename = "
                 "'{TABLE}';").format(
            SCHEMA=schema_name, TABLE=table
        )
        cursor.execute(query)
        if cursor.fetchone():
            print(
                "The table {Table} trying to onboard is already present in Transformation Master inside the schema you mentioned.".format(
                    Table=table))
        else:
            temp_table_list.append(table)
    table_names = temp_table_list
    return table_names

def dag_variable_enum_validator(cursor, field_name, value):
    """
    Validate if the given value exists for a specific field in dag_variable.
    Args:
        cursor: DB cursor
        field_name: either 'frequency' or 'job_group'
        value: the value to validate
    Raises:
        SystemExit if the value is not found
    """
    query = (
        f"SELECT JSON_UNQUOTE(JSON_EXTRACT(value, '$.{field_name}')) AS {field_name} "
        f"FROM datalake_config.dag_variable "
        f"WHERE JSON_VALID(value) = true "
        f"AND JSON_UNQUOTE(JSON_EXTRACT(value, '$.{field_name}')) = '{value}' "
        f"AND is_active = 'Y';"
    )
    cursor.execute(query)
    results = cursor.fetchall()

    if results:
        print(f"The input {field_name} '{value}' is valid in dag variable.")
    else:
        sys.exit(f"The input {field_name} is not existing in dag variable. Please kindly update and create the DAG first. Exiting...")

def table_name_checker(result_rds_endpoints, schema_name, table_names, env):
    rds_creds = {}
    temp_table_list = []
    rds_creds['host'] = result_rds_endpoints[0][1]
    rds_creds['port'] = result_rds_endpoints[0][2]
    rds_creds['user'] = result_rds_endpoints[0][3]
    rds_creds['password'] = get_vault_key(result_rds_endpoints[0][4], env)['DB_PASSWORD']
    conn = connect_mysql_db(rds_creds)
    cur = conn.cursor()
    print("Validating the input table names")
    for table in table_names:
        query = ("SHOW TABLES in {SCHEMA} like '{TABLE}';"
                 .format(SCHEMA=schema_name, TABLE=table)
                 )
        print(query)
        cur.execute(query)
        if not cur.fetchone():
            print("Wrong table name input. Please check the "
                  "table_name - {table}".format(table=table)
                  )
        else:
            temp_table_list.append(table)
    cur.close()
    conn.close()
    table_names = temp_table_list
    return table_names


def main():
    # AWS credentials and region configuration
    aws_region = 'ap-southeast-1'
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.getenv('AWS_SESSION_TOKEN')
    # Initialize the DMS client
    dms_client = boto3.client('dms', region_name=aws_region, aws_access_key_id=aws_access_key_id,
                              aws_secret_access_key=aws_secret_access_key, aws_session_token=aws_session_token)

    # Parameters from jenkins
    tgt_dbname = os.getenv('TargetDbName')
    src_dbname = tgt_dbname
    env = os.getenv('Environment')
    schema_name = os.getenv('SchemaName')
    execution_method = os.getenv('ExecutionMethod')
    partition_column = os.getenv('PartitionColumn')
    job_group = os.getenv('JobGroup')
    frequency_in_mins = os.getenv('Frequency')
    incr_key = os.getenv('IncrementalKey')
    table_names = os.getenv('TableNames')

    if not table_names or not schema_name or not tgt_dbname:
        sys.exit("Missing parameters. Exiting...")

    if partition_column:
        partition_column = partition_column.replace(",", "")
    if job_group:
        job_group = job_group.replace(",", "")
    if frequency_in_mins:
        if frequency_in_mins == ',':
            frequency_in_mins = frequency_in_mins.replace(",", "")
        else:
            frequency_in_mins = int(frequency_in_mins.replace(",", ""))
    if incr_key:
        incr_key = incr_key.replace(",", "")

    if not frequency_in_mins:
        frequency_in_mins = 360
    if not job_group:
        job_group = 'g6'
    if not incr_key:
        incr_key = 'updated_at'

    print("Parameters from Jenkins")
    # print("Replication Task Name = {replication_task_name}"
    #       .format(replication_task_name=replication_task_name))
    print("Src_DBName = {src_dbname}".format(src_dbname=src_dbname))
    print("Tgt_DBName = {tgt_dbname}".format(tgt_dbname=tgt_dbname))
    print("Schema Name = {schema_name}".format(schema_name=schema_name))
    print("Environment = {env}".format(env=env))
    print("Execution Method = {execution_method}"
          .format(execution_method=execution_method))
    print("Frequency = {frequency_in_mins}"
          .format(frequency_in_mins=frequency_in_mins))
    print("Job Group = {job_group}".format(job_group=job_group))
    print("Incremental Key = {incr_key}".format(incr_key=incr_key))
    print("Partition Column = {partition_column}"
          .format(partition_column=partition_column))
    table_names = table_names.replace(" ", "")
    table_names = table_names.split(",")
    print("Tables = {table_names}".format(table_names=table_names))

    if env == 'stage':
        config_host = DATALAKE_CONFIG_STAGE_HOST
        config_username = DATALAKE_CONFIG_STAGE_USER
        config_pass = os.getenv('DATALAKE_CONFIG_STAGE_PASSWORD')

    elif env == 'prod':
        config_host = DATALAKE_CONFIG_PROD_HOST
        config_username = DATALAKE_CONFIG_PROD_USER
        config_pass = os.getenv('DATALAKE_CONFIG_PROD_PASSWORD')
    else:
        sys.exit("Wrong env - {env}".format(env=env))
    try:
        connection = mysql.connector.connect(
            host=config_host,
            user=config_username,
            password=config_pass
        )
        print(f"Connecting to datalake-config-{env} database")
        cursor = connection.cursor()
        replication_task_name = get_dms_task_from_rds_endpoint(cursor, schema_name)
        if replication_task_name:
            print("Chosen Replication Task Name = {replication_task_name}"
                  .format(replication_task_name=replication_task_name))
        else:
            raise Exception("No DMS task found for the schema name in RDS Endpoints table.Kindly check")

        if execution_method == 'new-table':
            # keep original table_names for DMS mapping review
            # new_table_names = tables that are NOT yet in transformation_master (used for DB inserts)
            new_table_names = table_validator(cursor, schema_name, table_names)
            already_onboarded = [t for t in table_names if t not in new_table_names]
            dag_variable_enum_validator(cursor, "frequency",frequency_in_mins)
            dag_variable_enum_validator(cursor, "job_group", job_group)
        rds_endpoint_query = FETCH_RDS_ENDPOINT_QUERY.format(schema_name=schema_name)
        print("Fetching RDS Endpoints...\n {rds_endpoint_query}"
              .format(rds_endpoint_query=rds_endpoint_query))
        cursor.execute(rds_endpoint_query)
        result_rds_endpoints = cursor.fetchall()
        print("RDS Endpoints = {result_rds_endpoints}"
              .format(result_rds_endpoints=result_rds_endpoints))

        if not result_rds_endpoints:
            raise Exception("No entry found in the RDS Endpoint table for the schema name. Kindly Check")

        if execution_method == 'new-table':
            # table_name_checker uses original table_names — validates all requested tables exist in source MySQL
            table_names = table_name_checker(
                result_rds_endpoints,
                schema_name,
                table_names,
                env
            )
            # re-filter new_table_names in case table_name_checker removed any invalid tables
            new_table_names = [t for t in new_table_names if t in table_names]

        elif execution_method in ('new-column-with-full-load', 'new-column-without-full-load'):
            # precheck: skip entire pipeline if all columns already exist in transformation_master
            rds_creds = {
                'host': result_rds_endpoints[0][1],
                'port': result_rds_endpoints[0][2],
                'user': result_rds_endpoints[0][3],
                'password': get_vault_key(result_rds_endpoints[0][4], env)['DB_PASSWORD']
            }
            tables_with_new_columns = column_validator(cursor, schema_name, table_names, rds_creds)
            if not tables_with_new_columns:
                sys.exit("Error: All columns for the requested tables already exist in transformation_master. "
                      "Skipping entire pipeline (DMS and RDS updates).")
            table_names = tables_with_new_columns

        print("The table/s getting onboarded = {table_names}"
              .format(table_names=table_names))
    except mysql.connector.Error as err:
        print("Error while connecting to MySQL {err}".format(err=err))
        print("Kindly check the RDSEndpoint table for the schema name")
        sys.exit(1)

    if execution_method == 'new-column-without-full-load':
        print("Execution method is new-column-without-full-load.")
        update = sql_generator(execution_method, env, schema_name, src_dbname, tgt_dbname,
                               table_names, result_rds_endpoints, partition_column, incr_key, job_group,
                               frequency_in_mins)
        print("Executing Update query = {update}".format(update=update))
        try:
            statements = update.strip().split(';\n')
            print('Statements = ', statements)
            for statement in statements:
                if statement.strip():  # Check if the statement is not empty
                    print("\nExecuting statement = {statement}"
                          .format(statement=statement))
                    execute_query(cursor, statement)
                    connection.commit()
            print("Executed Update query")
            cursor.close()
            connection.close()
        except Exception as e:
            print(e.__str__())
        exit(0)
    else:
        scaled_up = False
        try:
            describe_response = describe_replication_task(dms_client=dms_client,
                                                          replication_task_name=replication_task_name)

            replication_task_arn = str(describe_response['ReplicationTasks'][0]['ReplicationTaskArn'])
            # modifying the existing table_mappings to include the new tables passed from jenkins
            current_table_mappings = describe_response['ReplicationTasks'][0]['TableMappings']
            table_mapping_dict = json.loads(current_table_mappings)

            # modifying the table mappings to include the new tables including transformation rules
            selection_rule = {}
            new_table_mappings_list = []
            selection_count = 0
            # collect tables already registered in DMS to avoid duplicates on rerun
            existing_dms_tables = {
                item['object-locator']['table-name']
                for item in table_mapping_dict['rules']
                if item['rule-type'] == 'selection'
            }
            print("DMS table mappings BEFORE modification: {tables}".format(tables=sorted(existing_dms_tables)))
            for item in table_mapping_dict['rules']:
                if item['rule-type'] == 'selection':
                    selection_count += 1
                    selection_rule = item
                    new_table_mappings_list.append(item)  # preserve existing selection rules
                else:
                    new_table_mappings_list.append(item)
            if selection_count == 0:
                raise Exception("Selection rule not found in the table mappings")
            single_table_mapping_obj = selection_rule

            for table in table_names:
                if table in existing_dms_tables:
                    # table already in DMS mappings — skip to avoid duplicate selection rules on rerun
                    print(f"Table {table} already exists in DMS mappings, skipping.")
                    continue
                temp_dict = single_table_mapping_obj.copy()
                temp_object_locator = {'schema-name': schema_name,
                                       'table-name': table}
                temp_dict['object-locator'] = temp_object_locator
                new_table_mappings_list.append(temp_dict)

            # rules are only include/exclude selection rules — overwrite rule-id
            # (and rule-name) sequentially across the whole list to guarantee uniqueness
            for idx, rule in enumerate(new_table_mappings_list, start=1):
                rule['rule-id'] = str(idx)
                rule['rule-name'] = str(idx)
            table_mapping_dict['rules'] = new_table_mappings_list
            new_table_mappings = json.dumps(table_mapping_dict)

            tables_after = [item['object-locator']['table-name'] for item in table_mapping_dict['rules'] if item['rule-type'] == 'selection']
            print("DMS table mappings AFTER modification: {tables}".format(tables=sorted(tables_after)))

            # modify the task FIRST — this is fast and surfaces mapping errors
            # (e.g. duplicate rule-id) immediately, before the slow instance resize
            modify_replication_task(dms_client=dms_client, replication_task_arn=replication_task_arn,
                                    new_table_mappings=new_table_mappings, migration_type=migration_type)
            print("Replication task is modified")
            # only now scale up the instance for the full load
            resize_replication_instance(env, dms_client, scale='up')
            scaled_up = True
            restart_replication_task(dms_client=dms_client, replication_task_arn=replication_task_arn)
            print("Replication task is restarted")
            resize_replication_instance(env, dms_client, scale='down')
            print("Replication instance is scaled down")
        except Exception as e:
            print("Error occurred during DMS steps {err}".format(err=e.__str__()))
            # only scale back down if we actually scaled up
            if scaled_up:
                print("Scaling down the replication instance")
                resize_replication_instance(env, dms_client, scale='down')
            sys.exit(1)
        try:
            if execution_method == 'new-table':
                if new_table_names:
                    # only generate and execute DB inserts for tables not yet onboarded
                    watermark, insert_statement = sql_generator(execution_method, env, schema_name, src_dbname, tgt_dbname,
                                                                new_table_names, result_rds_endpoints, partition_column,
                                                                incr_key, job_group, frequency_in_mins)

                    # precheck: filter out tables that already have a watermark entry to prevent duplicate rows on rerun
                    cursor.execute(
                        f"SELECT src_tablename FROM datalake_config.watermark WHERE src_schemaname = '{schema_name}' AND src_tablename IN ({','.join(repr(t) for t in new_table_names)})"
                    )
                    existing_watermark_tables = {row[0] for row in cursor.fetchall()}
                    tables_needing_watermark = [t for t in new_table_names if t not in existing_watermark_tables]

                    if tables_needing_watermark:
                        print("Executing Watermark query = {watermark}".format(watermark=watermark))
                        execute_query(cursor, watermark)
                        connection.commit()
                    else:
                        print("All tables already have watermark entries, skipping watermark insert.")

                    print("Executing Insert query = {insert_statement}".format(insert_statement=insert_statement))
                    execute_query(cursor, insert_statement)
                    connection.commit()
                else:
                    print("No new tables to insert — all requested tables are already onboarded. Skipping DB inserts.")

                cursor.close()
                connection.close()

                # DMS was reviewed/updated above — now fail the job so the user is aware tables already existed
                if already_onboarded:
                    sys.exit("Error: The following tables are already onboarded in transformation_master: {tables}. "
                             "DMS mapping was reviewed and updated, but no DB inserts were made for these tables.".format(tables=already_onboarded))
            elif execution_method == 'new-column-with-full-load':
                update = sql_generator(execution_method, env, schema_name, src_dbname, tgt_dbname,
                                       table_names, result_rds_endpoints, partition_column, incr_key, job_group,
                                       frequency_in_mins)
                # print("Executing Update query = ", update)
                statements = update.strip().split(';\n')
                # print('Statements = ', statements)
                try:
                    for statement in statements:
                        if statement.strip():  # Check if the statement is not empty
                            print("\nExecuting statement = {statement}"
                                  .format(statement=statement))
                            execute_query(cursor, statement)
                            connection.commit()
                    print("Executed Update query")
                    cursor.close()
                    connection.close()
                except Exception as e:
                    print(e.__str__())
            else:
                print("Wrong execution method - {execution_method}"
                      .format(execution_method=execution_method))
                sys.exit(1)
        except mysql.connector.Error as err:
            print("Error in Mysql Connection")
            print("Error while connecting to MySQL {err}".format(err=err))
        trigger_full_load_dag(env, dag_name, region)


if __name__ == '__main__':
    main()

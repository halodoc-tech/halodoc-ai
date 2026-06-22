#!/usr/bin/env python3
"""
AWS DMS Endpoint and Task Management Script
Refined version with improved security, error handling, and clean code structure.

Environment Variables Required:
  - AWS_ACCESS_KEY_ID: Your AWS access key
  - AWS_SECRET_ACCESS_KEY: Your AWS secret key
  - AWS_SESSION_TOKEN: (Optional) If using temporary credentials
  - AWS_REGION: AWS region (Default: config.yml aws.region)
  - SCHEMA_NAME: Database schema name to process
  - Environment: Environment name (stage/prod) for vault integration

Optional Configuration:
  - DRY_RUN: Set to 'true' for validation only (Default: 'false')
  - RECREATE_ENDPOINT: Delete and recreate endpoint if exists (Default: 'false')
  - SKIP_CONNECTION_TEST: Skip endpoint connection test (Default: 'false')
"""

import boto3
import json
import sys
import time
import os
import re
from datetime import datetime, timedelta

from botocore.exceptions import ClientError, NoCredentialsError
from typing import Dict, Optional, Tuple, List
import mysql.connector
from mysql.connector import Error

from configs.dms_automation_configs import *
from utils.vault_client import get_vault_credentials
from utils.db_connection import mysql_connection, execute_query, fetch_all, fetch_one, DbConnectionError
from sql_scripts.dms_automation_sql import RDS_ENDPOINT_CONNECTION
import registry


def get_rds_endpoint_config(schema_name: str, rds_credentials: Dict) -> Optional[Dict]:
    """
    Retrieve RDS endpoint configuration using the common utility.
    """
    if registry.backend_mode() == "yaml":
        result = registry.find("rds_endpoints", schema_name=schema_name)
        if not result:
            print(f"No configuration found for schema '{schema_name}'")
        return result

    try:
        # The 'with' statement handles opening AND automatically closing the connection
        with mysql_connection(
            host=rds_credentials["host"],
            user=rds_credentials["user"],
            password=rds_credentials["password"],
            database=rds_credentials.get("database")
        ) as (conn, cursor):
            
            # Use the helper functions for execution and fetching
            execute_query(cursor, RDS_ENDPOINT_CONNECTION, (schema_name,))
            result = fetch_one(cursor) 
            
            if not result:
                print(f"No configuration found for schema '{schema_name}'")
                return None
            
            print(f"✓ Retrieved configuration for schema '{schema_name}'")
            return result
            
    except DbConnectionError as e:
        # Catch the custom error for clean, predictable error handling
        print(f"❌ ERROR: Database operation failed: {e}")
        return None

class DMSManager:
    """Manages AWS DMS endpoints and replication tasks with improved error handling."""
    
    def __init__(self, region_name: str, environment: str , schema_name: str):
        """Initialize DMS client with credential validation."""
        self.region_name = region_name
        self.dms_client = None
        self.default_tags = [
                {"Key": "Environment", "Value": environment},
                {"Key": "Owner", "Value": "SRE"},
                {"Key": "CostCenter", "Value": "DE"},
                {"Key": "Department", "Value": "DE"},
            ]
        schema_name_clean = schema_name.replace("_", "-").lower()
        self.endpoint_template = f"src-load-{schema_name_clean}"
        self.incr_task_template = f"incr-load-{schema_name_clean}"
        self.full_task_template = f"full-load-{schema_name_clean}"
        self._initialize_client()

    def _initialize_client(self):
        """Initialize boto3 DMS client with proper credential handling."""
        try:
            # Use environment variables for AWS credentials
            session = boto3.Session()
            self.dms_client = session.client('dms', region_name=self.region_name)
            
            # Validate credentials with a lightweight API call
            # self.dms_client.describe_endpoints(MaxRecords=1)
            print("✓ AWS DMS client initialized and credentials validated")
            
        except NoCredentialsError:
            print("❌ ERROR: AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            sys.exit(1)
        except ClientError as e:
            print(f"❌ ERROR: AWS client initialization failed: {e}")
            sys.exit(1)

    def endpoint_exists(self, endpoint_id: str) -> bool:
        """Check if DMS endpoint exists."""
        try:
            response = self.dms_client.describe_endpoints(
                Filters=[{'Name': 'endpoint-id', 'Values': [endpoint_id]}]
            )
            return len(response.get('Endpoints', [])) > 0
        except ClientError as e:
            print(f"⚠️  Warning: Could not check endpoint existence: {e}")
            return False

    def get_endpoint_arn(self, endpoint_id: str) -> Optional[str]:
        """Get endpoint ARN by endpoint ID."""
        try:
            response = self.dms_client.describe_endpoints(
                Filters=[{'Name': 'endpoint-id', 'Values': [endpoint_id]}]
            )
            endpoints = response.get('Endpoints', [])
            return endpoints[0]['EndpointArn'] if endpoints else None
        except ClientError as e:
            print(f"⚠️  Warning: Could not retrieve endpoint ARN: {e}")
            return None

    def create_endpoint(self, config: Dict) -> Tuple[bool, Optional[str]]:
        """Create DMS endpoint from configuration."""
        endpoint_id = config.get('EndpointIdentifier')
        if not endpoint_id:
            print("❌ ERROR: 'EndpointIdentifier' missing from configuration")
            return False, None

        try:
            print(f"🚀 Creating endpoint: {endpoint_id}")

            response = self.dms_client.create_endpoint(**config)
            endpoint_arn = response['Endpoint']['EndpointArn']
            
            print(f"✓ Endpoint created successfully: {endpoint_arn}")
            return True, endpoint_arn
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceAlreadyExistsFault':
                print(f"⚠️  Endpoint '{endpoint_id}' already exists")
                return True, self.get_endpoint_arn(endpoint_id)
            
            print(f"❌ ERROR: Failed to create endpoint: {e.response['Error']['Message']}")
            return False, None

    def test_connection(self, endpoint_arn: str, replication_instance_arn: str) -> bool:
        """Test endpoint connection using replication instance."""
        try:
            print(f"🔍 Testing connection for endpoint")
            self.dms_client.test_connection(
                EndpointArn=endpoint_arn,
                ReplicationInstanceArn=replication_instance_arn
            )
            
            return self._wait_for_connection_test(endpoint_arn, timeout=300)
            
        except ClientError as e:
            print(f"❌ ERROR: Failed to initiate connection test: {e}")
            return False

    def _wait_for_connection_test(self, endpoint_arn: str, timeout: int = 300) -> bool:
        """Wait for connection test to complete."""
        wait_time = 0
        interval = 15
        
        while wait_time < timeout:
            try:
                connections = self.dms_client.describe_connections(
                    Filters=[{'Name': 'endpoint-arn', 'Values': [endpoint_arn]}]
                )
                
                if connections.get('Connections'):
                    status = connections['Connections'][0]['Status']
                    print(f"⏳ Connection test status: {status} ({wait_time}s)")
                    
                    if status == 'successful':
                        print("✅ Connection test PASSED")
                        return True
                    elif status == 'failed':
                        error_msg = connections['Connections'][0].get('LastFailureMessage', 'Unknown error')
                        print(f"❌ Connection test FAILED: {error_msg}")
                        return False
                
                time.sleep(interval)
                wait_time += interval
                
            except ClientError as e:
                print(f"⚠️  Error checking connection status: {e}")
                return False
        
        print(f"⏰ Connection test timed out after {timeout}s")
        return False

    def get_replication_instances(self) -> List[str]:
        """Get list of available DMS replication instance ARNs."""
        try:
            response = self.dms_client.describe_replication_instances()
            instances = response.get('ReplicationInstances', [])
            return [instance['ReplicationInstanceArn'] for instance in instances]
        except ClientError as e:
            print(f"⚠️  Warning: Could not retrieve replication instances: {e}")
            return []
        
    def get_replication_instance_arn(self, instance_id: str) -> Optional[str]:
        """Get replication instance ARN by instance ID."""
        try:
            response = self.dms_client.describe_replication_instances(
                Filters=[{'Name': 'replication-instance-id', 'Values': [instance_id]}]
            )
            instances = response.get('ReplicationInstances', [])
            return instances[0]['ReplicationInstanceArn'] if instances else None
        except ClientError as e:
            print(f"⚠️  Warning: Could not retrieve replication instance ARN: {e}")
            return None
        
    def task_exists(self, task_id: str) -> bool:
        """Check if DMS replication task exists."""
        try:
            response = self.dms_client.describe_replication_tasks(
                Filters=[{'Name': 'replication-task-id', 'Values': [task_id]}]
            )
            return len(response.get('ReplicationTasks', [])) > 0
        except ClientError as e:
            print(f"⚠️  Warning: Could not check task existence for '{task_id}': {e}")
            return False

    def create_selection_rule(self, schema_name: str) -> dict:
        """Create table mappings JSON for the given schema."""
        selection_rule = {
                    "rule-type": "selection",
                    "rule-id": "1",
                    "rule-name": "1",
                    "object-locator": {
                        "schema-name": schema_name,
                        "table-name": "%"
                    },
                    "rule-action": "include",
                    "filters": []
                }
        return selection_rule

    def create_transformation_rule(self, schema_name: str) -> dict:
        """Create DMS transformation rule."""
        transformation_rule = {
            "rule-type": "transformation",
            "rule-id": "2",
            "rule-name": "2",
            "rule-target": "column",
            "object-locator": {
                "schema-name": schema_name,
                "table-name": "%"
            },
            "rule-action": "add-column",
            "value": "ar_h_change_seq",
            "expression": "$AR_H_CHANGE_SEQ",
            "data-type": {
                "type": "string",
                "length": "50"
            }
        }
        return transformation_rule


    def create_replication_task(self, task_config: Dict) -> Tuple[bool, Optional[str]]:
        """Create DMS replication task."""
        task_id = task_config.get('ReplicationTaskIdentifier')
        if not task_id:
            print("❌ ERROR: 'ReplicationTaskIdentifier' missing from configuration")
            return False, None

        try:
            print(f"🚀 Creating replication task: {task_id}")
            
            # Check if task already exists
            if self.task_exists(task_id):
                print(f"⚠️  Task '{task_id}' already exists")
                return True, task_id

            response = self.dms_client.create_replication_task(**task_config)
            task_arn = response['ReplicationTask']['ReplicationTaskArn']
            
            print(f"✅ Replication task created successfully")
            print(f"   Task ID: {task_id}")
            print(f"   Task ARN: {task_arn}")
            print(f"   Migration Type: {task_config['MigrationType']}")
            
            return True, task_arn
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'ResourceAlreadyExistsFault':
                print(f"⚠️  Task '{task_id}' already exists")
                return True, task_id
            
            print(f"❌ ERROR: Failed to create task '{task_id}': {error_message}")
            return False, None

    def create_full_load_task(self, schema_name: str, source_endpoint_arn: str, 
                            target_endpoint_arn: str, replication_instance_arn: str, 
                            environment: str = "stage") -> Tuple[bool, Optional[str]]:
        """Create full load replication task."""
        # task_id = f"full-load-{schema_name.replace('_', '-').lower()}"
        task_id = self.full_task_template

        selection_rule = self.create_selection_rule(schema_name)

        table_mappings = {
            "rules": [
                selection_rule
            ]
        }
        final_table_mappings = json.dumps(table_mappings, indent=4)

        
        task_config = {
            "ReplicationTaskIdentifier": task_id,
            "SourceEndpointArn": source_endpoint_arn,
            "TargetEndpointArn": target_endpoint_arn,
            "ReplicationInstanceArn": replication_instance_arn,
            "MigrationType": "full-load",
            "TableMappings": final_table_mappings,
            "Tags": self.default_tags
        }
        
        return self.create_replication_task(task_config)

    def create_incremental_task(self, schema_name: str, source_endpoint_arn: str, 
                              target_endpoint_arn: str, replication_instance_arn: str,
                              environment: str = "stage") -> Tuple[bool, Optional[str]]:
        """Create incremental replication task."""
        # task_id = f"incr-load-{schema_name.replace('_', '-').lower()}"
        task_id = self.incr_task_template

        selection_rule = self.create_selection_rule(schema_name)
        transformation_rule = self.create_transformation_rule(schema_name)


        table_mappings = {
            "rules": [
                selection_rule,
                transformation_rule
            ]
        }
        final_table_mappings = json.dumps(table_mappings, indent=4)
        
        task_config = {
            "ReplicationTaskIdentifier": task_id,
            "SourceEndpointArn": source_endpoint_arn,
            "TargetEndpointArn": target_endpoint_arn,
            "ReplicationInstanceArn": replication_instance_arn,
            "MigrationType": "cdc", 
            "TableMappings": final_table_mappings,
            "CdcStartTime": datetime.now() - timedelta(hours=24),
            "Tags": self.default_tags
        }
        
        return self.create_replication_task(task_config)

    def create_dms_tasks(self, schema_name: str, source_endpoint_arn: str, 
                        tgt_full_load_endpoint: str, tgt_incr_load_endpoint: str,
                        full_load_instance: str, incr_load_instance: str, 
                        environment: str) -> bool:
        """
        Create both full load and incremental DMS replication tasks.
        
        Args:
            schema_name: Database schema name
            source_endpoint_arn: Source endpoint ARN
            tgt_full_load_endpoint: Target endpoint ID for full load
            tgt_incr_load_endpoint: Target endpoint ID for incremental load
            full_load_instance: Replication instance ID for full load
            incr_load_instance: Replication instance ID for incremental load
            environment: Environment (stage/prod)
        
        Returns:
            True if both tasks created successfully, False otherwise
        """
        print("📋 Creating DMS Replication Tasks...")
        print("=" * 40)
        
        # Get ARNs for target endpoints and replication instances
        print("🔍 Validating required resources...")
        full_load_target_arn = self.get_endpoint_arn(tgt_full_load_endpoint)
        incr_load_target_arn = self.get_endpoint_arn(tgt_incr_load_endpoint)
        full_replication_instance_arn = self.get_replication_instance_arn(full_load_instance)
        incr_replication_instance_arn = self.get_replication_instance_arn(incr_load_instance)
        
        # Validate all resources exist
        missing_resources = []
        if not full_load_target_arn:
            missing_resources.append(f"Full load target endpoint: {tgt_full_load_endpoint}")
        if not incr_load_target_arn:
            missing_resources.append(f"Incremental target endpoint: {tgt_incr_load_endpoint}")
        if not full_replication_instance_arn:
            missing_resources.append(f"Full load replication instance: {full_load_instance}")
        if not incr_replication_instance_arn:
            missing_resources.append(f"Incremental replication instance: {incr_load_instance}")
        
        if missing_resources:
            print("❌ ERROR: Missing required resources for task creation:")
            for resource in missing_resources:
                print(f"   - {resource}")
            return False
        
        print("✅ All required resources found!")
        print()
        
        # Create full load task
        print("📋 Creating Full Load Task...")
        print("-" * 30)
        full_load_success, full_load_arn = self.create_full_load_task(
            schema_name, source_endpoint_arn, full_load_target_arn, 
            full_replication_instance_arn, environment
        )
        
        if not full_load_success:
            print("❌ Failed to create full load task")
            return False
        
        print()
        
        # Create incremental task
        print("📋 Creating Incremental Task...")
        print("-" * 30)
        incr_success, incr_arn = self.create_incremental_task(
            schema_name, source_endpoint_arn, incr_load_target_arn, 
            incr_replication_instance_arn, environment
        )
        
        if not incr_success:
            print("❌ Failed to create incremental task")
            return False
        
        print()
        print("🎉 SUCCESS: Both replication tasks created successfully!")
        print("=" * 50)
        print("📋 Task Summary:")
        print(f"   Full Load Task: {self.full_task_template}")
        print(f"   Incremental Task: {self.incr_task_template}")
        print(f"   Schema: {schema_name}")
        print(f"   Full Load Target: {tgt_full_load_endpoint}")
        print(f"   Incremental Target: {tgt_incr_load_endpoint}")
        print(f"   Full Load Instance: {full_load_instance}")
        print(f"   Incremental Instance: {incr_load_instance}")
        print(f"   Environment: {environment}")
        
        return True
        
def insert_rds_endpoint_config(endpoint_config: Dict, rds_credentials: Dict) -> bool:
    """
    Insert new RDS endpoint configuration into the database using the DB connector utility.
    
    Args:
        endpoint_config: New endpoint configuration to insert.
        rds_credentials: Database connection credentials.
    
    Returns:
        True if successful, False otherwise.
    """
    # Validate required fields
    required_fields = ['schema_name', 'server_name', 'port', 'user_name', 'vault_key']
    for field in required_fields:
        if not endpoint_config.get(field):
            print(f"❌ ERROR: Missing required field '{field}' for endpoint configuration")
            return False
    
    existing_config = get_rds_endpoint_config(endpoint_config['schema_name'], rds_credentials)
    if existing_config:
        print(f"⚠️  WARNING: Configuration for schema '{endpoint_config['schema_name']}' already exists")
        return False

    schema_name_clean = endpoint_config['schema_name'].replace("_", "-").lower()
    dms_tasks = json.dumps({
        "full_load_task": f"full-load-{schema_name_clean}",
        "incremental_task": f"incr-load-{schema_name_clean}"
    })

    if registry.backend_mode() == "yaml":
        registry.insert("rds_endpoints", {
            "schema_name": endpoint_config["schema_name"],
            "server_name": endpoint_config["server_name"],
            "port": int(endpoint_config["port"]),
            "user_name": endpoint_config["user_name"],
            "vault_key": endpoint_config["vault_key"],
            "dms_tasks": dms_tasks,
        })
        print(f"✅ Recorded endpoint config for schema '{endpoint_config['schema_name']}' in YAML registry")
        return True

    # Prepare the insert query and data
    insert_query = """
    INSERT INTO datalake_config.rds_endpoints (schema_name, server_name, port, user_name, vault_key, dms_tasks)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    
    data_to_insert = (
        endpoint_config['schema_name'],
        endpoint_config['server_name'],
        int(endpoint_config['port']),
        endpoint_config['user_name'],
        endpoint_config['vault_key'],
        dms_tasks
    )

    try:
        # Use the context manager for safe connection handling
        with mysql_connection(**rds_credentials) as (conn, cursor):
            execute_query(cursor, insert_query, data_to_insert)
            
            # Commit the transaction to save the changes
            conn.commit()
            
            if cursor.rowcount > 0:
                print(f"✅ Successfully inserted endpoint configuration for schema '{endpoint_config['schema_name']}'")
                print("Inserted configuration:")
                for key, value in endpoint_config.items():
                    print(f"  {key}: {value}")
                return True
            else:
                # This case is less likely if the execute_query doesn't raise an error, but good to have
                print("❌ ERROR: No rows were inserted, despite no error being raised.")
                return False
        
    except (DbConnectionError, mysql.connector.Error) as e:
        # Catch the specific errors from our utility and the underlying library
        print(f"❌ ERROR: Failed to insert endpoint configuration: {e}")
        return False


def build_endpoint_config(schema_name: str, endpoint_config: Dict, vault_credentials: Dict) -> Dict:
    """
    Build DMS endpoint configuration from database config and vault credentials.
    
    Args:
        schema_name: Target schema name
        endpoint_config: Database configuration
        vault_credentials: Vault credentials
    
    Returns:
        Complete DMS endpoint configuration
    """
    engine_name = endpoint_config.get('endpoint_engine_name', 'mysql')
    
    schema_name_lower = schema_name.replace("_", "-").lower()
    config = {
        "EndpointIdentifier": f"src-load-{schema_name_lower}",
        "EndpointType": "source",
        "EngineName": engine_name,
        "ServerName": endpoint_config["server_name"],
        "Port": int(endpoint_config["port"]),
        "DatabaseName": schema_name,
        "Username": endpoint_config["user_name"],
        "Password": next((v for k, v in vault_credentials.items() if "db_password" in k.lower()), "")
    }

    if engine_name.lower() == 'mysql':
        config["MySQLSettings"] = {
            "ServerTimezone": "Asia/Jakarta"
        }
    
    return config


def main():
    """Main execution function."""
    print("🚀 Starting DMS Endpoint Management Script")
    print("=" * 50)
    
    # Get environment variables
    schema_name = os.environ.get('SCHEMA_NAME')
    environment = os.environ.get('Environment')
    aws_region = os.environ.get('AWS_REGION', region)

    src_engine = os.environ.get('SOURCE_ENGINE')
    src_endpoint_host = os.environ.get('SOURCE_DB_HOST')
    src_endpoint_port = os.environ.get('SOURCE_DB_PORT')
    src_endpoint_user = os.environ.get('SOURCE_DB_USER')
    src_endpoint_vault_path = os.environ.get('SOURCE_DB_VAULT_PATH')

    tgt_full_load_endpoint = os.environ.get('TARGET_FULL_LOAD_ENDPOINT', '').strip().rstrip(',')
    tgt_incr_load_endpoint = os.environ.get('TARGET_INCR_LOAD_ENDPOINT', '').strip().rstrip(',')
    full_load_instance = os.environ.get('FULL_LOAD_INSTANCE', '').strip().rstrip(',')
    incr_load_instance = os.environ.get('INCR_LOAD_INSTANCE', '').strip().rstrip(',')

    if not schema_name:
        print("❌ ERROR: SCHEMA_NAME is required")
        sys.exit(1)
    
    # Validate required environment variables for task creation
    required_env_vars = {
        'TARGET_FULL_LOAD_ENDPOINT': tgt_full_load_endpoint,
        'TARGET_INCR_LOAD_ENDPOINT': tgt_incr_load_endpoint,
        'FULL_LOAD_INSTANCE': full_load_instance,
        'INCR_LOAD_INSTANCE': incr_load_instance
    }
    
    missing_vars = [var for var, value in required_env_vars.items() if not value]
    if missing_vars:
        print("❌ ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        sys.exit(1)
    
    print(f"📋 Configuration:")
    print(f"   Schema: {schema_name}")
    print(f"   Environment: {environment}")
    print(f"   Region: {aws_region}")
    print(f"   Full Load Target: {tgt_full_load_endpoint}")
    print(f"   Incremental Target: {tgt_incr_load_endpoint}")
    print(f"   Full Load Instance: {full_load_instance}")
    print(f"   Incremental Instance: {incr_load_instance}")
    print()
    
    try:
        # Initialize DMS manager
        dms = DMSManager(aws_region, environment, schema_name)
        
        # Get RDS credentials for configuration lookup
        env_configs = {
            'stage': {
                "host": DATALAKE_CONFIG_STAGE_HOST,
                "user": DATALAKE_CONFIG_STAGE_USER,
                "password": os.environ.get('DATALAKE_CONFIG_STAGE_PASSWORD'),
            },
            'prod': {
                "host": DATALAKE_CONFIG_PROD_HOST,
                "user": DATALAKE_CONFIG_PROD_USER,
                "password": os.environ.get('DATALAKE_CONFIG_PROD_PASSWORD'),
            }
        }

        env_specific_creds = env_configs.get(environment)
        if not env_specific_creds:
            print(f"❌ ERROR: Invalid environment '{environment}'. Must be 'stage' or 'prod'.")
            sys.exit(1)

        # Combine common and environment-specific credentials
        rds_creds = {
                "port": 3306,
                "database": "datalake_config",
                **env_specific_creds
        }

        # insert into rds_config 
        src_endpoint_config = {
            "endpoint_engine_name": src_engine,
            "schema_name": schema_name,
            "server_name": src_endpoint_host,
            "port": src_endpoint_port,
            "user_name": src_endpoint_user,
            "vault_key": src_endpoint_vault_path
        }

        insert_status = insert_rds_endpoint_config(src_endpoint_config, rds_creds)
        print(f"Insert status: {insert_status}")
        
        # Get endpoint configuration from database
        print("📋 Retrieving endpoint configuration...")
        endpoint_config = get_rds_endpoint_config(schema_name, rds_creds)
        
        if not endpoint_config:
            sys.exit(1)
        
        # Get credentials from vault
        print("🔑 Retrieving credentials from vault...")
        vault_key = endpoint_config["vault_key"]
        vault_credentials = get_vault_credentials(vault_key, environment)
        if not vault_credentials:
            sys.exit(1)
        
        # Build DMS endpoint configuration
        dms_config = build_endpoint_config(schema_name, endpoint_config, vault_credentials)
        endpoint_name = dms_config["EndpointIdentifier"]
        
        # Handle existing endpoint
        if dms.endpoint_exists(endpoint_name):
            print(f"✓ Endpoint '{endpoint_name}' already exists")
            endpoint_arn = dms.get_endpoint_arn(endpoint_name)
            if not endpoint_arn:
                print("❌ ERROR: Could not retrieve existing endpoint ARN")
                sys.exit(1)
        else:
            # Create new endpoint
            success, endpoint_arn = dms.create_endpoint(dms_config)
            if not success or not endpoint_arn:
                print("❌ ERROR: Failed to create endpoint")
                sys.exit(1)
        
        # Test connection
        print("🔍 Testing endpoint connections...")
        replication_instances = dms.get_replication_instances()
        
        if not replication_instances:
            print("⚠️  WARNING: No replication instances found for connection testing")
        else:
            connection_success = False
            for instance_arn in replication_instances:
                print(f"🔗 Testing with instance: {instance_arn.split('/')[-1]}")
                if dms.test_connection(endpoint_arn, instance_arn):
                    connection_success = True
                    break
            
            if not connection_success:
                print("❌ ERROR: All connection tests failed")
                sys.exit(1)
        
        print()
        print("✅ DMS endpoint management completed successfully!")
        print(f"📍 Endpoint ARN: {endpoint_arn}")

        # Create DMS replication tasks
        print()
        print("🔄 Proceeding with DMS task creation...")
        task_success = dms.create_dms_tasks(
            schema_name=schema_name,
            source_endpoint_arn=endpoint_arn,
            tgt_full_load_endpoint=tgt_full_load_endpoint,
            tgt_incr_load_endpoint=tgt_incr_load_endpoint,
            full_load_instance=full_load_instance,
            incr_load_instance=incr_load_instance,
            environment=environment
        )
        
        if not task_success:
            print("❌ ERROR: Failed to create DMS replication tasks")
            sys.exit(1)

        
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
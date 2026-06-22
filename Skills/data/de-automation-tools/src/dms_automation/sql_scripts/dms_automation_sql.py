RDS_ENDPOINT_CONNECTION = """
SELECT schema_name, 
	server_name, 
    port, 
    user_name, 
    vault_key
    FROM datalake_config.rds_endpoints
    WHERE schema_name = %s
"""
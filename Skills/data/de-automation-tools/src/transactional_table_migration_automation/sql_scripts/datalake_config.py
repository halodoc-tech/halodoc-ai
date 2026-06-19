FETCH_RDS_ENDPOINT_QUERY = """
SELECT
	schema_name
	, server_name
	, port
	, user_name
	, vault_key
FROM
	datalake_config.rds_endpoints
WHERE
	schema_name = '{schema_name}'
"""

INSERT_QUERY = """
INSERT INTO datalake_config.transformation_master
(src_dbname, src_schemaname, src_tablename, src_s3_path, tgt_s3_path, tgt_dbname, tgt_schemaname, tgt_tablename, key_column, precombine, incremental_key,tgt_partitionkey, tgt_loadtype, active_flag, src_incr_s3_path, status, tgt_schema_definition,   add_source_header, source_header, is_transform, transform_logic, hudi_parallelism, frequency_in_mins,job_group, clustering_enabled, enable_hudi_index)
VALUES 
{COLUMN_VALUES};
"""
UPDATE_COLUMN_QUERY = """
UPDATE datalake_config.transformation_master set tgt_schema_definition = '{schema_doc}' where src_tablename = '{table_name}' and src_schemaname = '{schema_name}'
"""
UPDATE_COLUMN_WITH_STATUS_QUERY = """
UPDATE datalake_config.transformation_master set tgt_schema_definition = '{schema_doc}', status='ready' where src_tablename = '{table_name}' and src_schemaname = '{schema_name}'
"""

INSERT_QUERY_WATERMARK = """
INSERT INTO datalake_config.watermark (src_schemaname, src_tablename) 
values 
{COLUMN_VALUES};
"""

SCHEMA_DEF_QUERY = """
SELECT
column_name, (CASE WHEN data_type = 'decimal' THEN column_type ELSE data_type END)
AS
data_type
FROM
INFORMATION_SCHEMA.columns
WHERE
table_schema = '{0}'
AND
table_name = '{1}'
ORDER
BY
ordinal_position
ASC
"""
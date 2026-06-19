INSERT_INTO_GSHEET_EXPORT = """
INSERT into datalake_config.gsheet_export(
	source,
    sheetname,
    sheet_id,
    sheet_range,
    target_s3_bucket,
    target_s3_prefix,
    business_unit,
    active_flag,
    job_group
)
VALUES
('gsheet','{new_table_name}','{sheet_id}','{sheet_range}','{bucket_prefix}-{env}','raw/fileupload/source=gsheet','{business_unit}','Y','{job_group}');
"""

UPDATE_GSHEET_EXPORT = """
UPDATE datalake_config.gsheet_export
SET sheet_range = '{sheet_range}'
WHERE sheet_id = '{sheet_id}' and sheet_range like '{tgt_sheet_name}!%';
"""
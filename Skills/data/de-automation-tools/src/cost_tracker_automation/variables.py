# Cost tracker config — connection values load from the skill's config.yml.
# Secrets stay in env vars (see src/README.md).
import os as _os, pathlib as _pathlib, yaml as _yaml


def _load():
    _p = _os.environ.get("DE_CONFIG_PATH")
    if not _p:
        for _par in _pathlib.Path(__file__).resolve().parents:
            if (_par / "config.yml").exists():
                _p = _par / "config.yml"
                break
    with open(_p) as _f:
        return _yaml.safe_load(_f) or {}


_C = _load()
_RS = _C["databases"]["redshift"]
_DL = _C["databases"]["datalake_config"]

redshift_host = _RS["host"]
redshift_port = str(_RS["port"])
redshift_dbname = _RS["db_name"]
redshift_user = _RS["user"]
redshift_cluster_name = _RS["cluster_name"]
datalake_host = _DL["prod_host"]
datalake_port = _DL["port"]
datalake_uname = _DL["prod_user"]
datalake_db = _DL["db_name"]
datalake_config_prod_host = _DL["prod_host"]
datalake_config_prod_user = _DL["prod_user"]
prod_airflow_env_name = _C["airflow"]["prod_env_name"]

key_dict = {
        "AWS CloudTrail": "CloudTrail($)",
        "AWS Config": "Config($)",
        "AWS Database Migration Service": "DMS($)",
        "AWS Glue": "Glue($)",
        "AWS Key Management Service": "Key Management Service($)",
        "AWS Lambda": "Lambda($)",
        "AWS Secrets Manager": "Secrets Manager($)",
        "AWS WAF": "WAF($)",
        "Amazon DynamoDB": "DynamoDB($)",
        "EC2 - Other": "EC2-Other($)",
        "Amazon Elastic Compute Cloud - Compute": "EC2-Instances($)",
        "Amazon Elastic Container Service for Kubernetes": "Elastic Container Service for Kubernetes($)",
        "Amazon Elastic MapReduce": "Elastic MapReduce($)",
        "Amazon GuardDuty": "GuardDuty($)",
        "Amazon Managed Workflows for Apache Airflow": "Managed Workflows for Apache Airflow($)",
        "Amazon Redshift": "Redshift($)",
        "Amazon Relational Database Service": "Relational Database Service($)",
        "Amazon Simple Notification Service": "SNS($)",
        "Amazon Simple Queue Service": "SQS($)",
        "Amazon Simple Storage Service": "S3($)",
        "Amazon Virtual Private Cloud": "VPC($)",
        "AmazonCloudWatch": "CloudWatch($)",
        "Tax": "Tax($)",
        "Amazon Athena": "Athena($)"
    }
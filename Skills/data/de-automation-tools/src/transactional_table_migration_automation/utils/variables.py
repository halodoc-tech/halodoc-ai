# Transactional migration config — load from the skill's config.yml.
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
_T = _C["transactional"]
_DMS = _C["dms"]

migration_type = _T["migration_type"]
upscale_instance_class = _T["upscale_instance_class"]
down_instance_class = _T["down_instance_class"]
stage_full_load_replication_instance_arn = _DMS["stage"]["full_load_replication_instance_arn"]
prod_full_load_replication_instance_arn = _DMS["prod"]["full_load_replication_instance_arn"]
dag_name = _T["dag_name"]
region = _C["aws"]["region"]
stage_airflow_env_name = _C["airflow"]["stage_env_name"]
prod_airflow_env_name = _C["airflow"]["prod_env_name"]
stage_vault_base_url = _C["vault"]["stage_base_url"]
prod_vault_base_url = _C["vault"]["prod_base_url"]

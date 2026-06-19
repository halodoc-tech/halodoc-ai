# GSheet onboarding config — crawler/DAG/env names load from the skill's config.yml.
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
_G = _C["gsheet"]

stage_crawler_name = _G["stage_crawler_name"]
prod_crawler_name = _G["prod_crawler_name"]
dag_name = _G["dag_name"]
stage_airflow_env_name = _C["airflow"]["stage_env_name"]
prod_airflow_env_name = _C["airflow"]["prod_env_name"]
datalake_bucket_prefix = _C["aws"]["datalake_bucket_prefix"]

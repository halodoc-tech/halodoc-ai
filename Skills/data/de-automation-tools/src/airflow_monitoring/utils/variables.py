# Airflow monitoring config — env names load from the skill's config.yml.
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

stage_airflow_env_name = _C["airflow"]["stage_env_name"]
prod_airflow_env_name = _C["airflow"]["prod_env_name"]
components = {'Metadatabase': 'not_healthy',
              'Scheduler': 'not_healthy',
              'Triggerer': 'not_healthy',
              'Dagprocessor': 'not_healthy'
              }

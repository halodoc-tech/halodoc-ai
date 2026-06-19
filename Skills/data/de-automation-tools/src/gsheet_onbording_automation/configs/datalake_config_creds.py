# datalake_config DB hosts — load from the skill's config.yml.
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


_DB = _load()["databases"]["datalake_config"]

DATALAKE_CONFIG_STAGE_HOST = _DB["stage_host"]
DATALAKE_CONFIG_STAGE_USER = _DB["stage_user"]
DATALAKE_CONFIG_PROD_HOST = _DB["prod_host"]
DATALAKE_CONFIG_PROD_USER = _DB["prod_user"]

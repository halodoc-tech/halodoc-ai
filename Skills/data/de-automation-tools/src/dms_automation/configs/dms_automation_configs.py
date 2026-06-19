# DMS automation config — values load from the skill's config.yml.
# Fill config.yml for your environment; secrets stay in env vars (see src/README.md).
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
_DB = _C["databases"]["datalake_config"]
_DMS = _C["dms"]

region = _C["aws"]["region"]

DATALAKE_CONFIG_STAGE_HOST = _DB["stage_host"]
DATALAKE_CONFIG_STAGE_USER = _DB["stage_user"]

DMS_FULL_LOAD_ENDPOINT_STAGE_ID = _DMS["stage"]["full_load_endpoint_id"]
DMS_INCR_LOAD_ENDPOINT_STAGE_ID = _DMS["stage"]["incr_load_endpoint_id"]
DMS_FULL_LOAD_INSTANCE_STAGE_ID = _DMS["stage"]["full_load_instance_id"]
DMS_INCR_LOAD_INSTANCE_STAGE_ID = _DMS["stage"]["incr_load_instance_id"]

DATALAKE_CONFIG_PROD_HOST = _DB["prod_host"]
DATALAKE_CONFIG_PROD_USER = _DB["prod_user"]

DMS_FULL_LOAD_ENDPOINT_PROD_ID = _DMS["prod"]["full_load_endpoint_id"]
DMS_INCR_LOAD_ENDPOINT_PROD_ID = _DMS["prod"]["incr_load_endpoint_id"]
DMS_FULL_LOAD_INSTANCE_PROD_ID = _DMS["prod"]["full_load_instance_id"]
DMS_INCR_LOAD_INSTANCE_PROD_ID = _DMS["prod"]["incr_load_instance_id"]

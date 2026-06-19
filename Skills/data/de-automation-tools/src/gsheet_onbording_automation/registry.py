"""Local YAML registry — active when config.yml backend.mode == 'yaml'.

Replaces datalake_config (MySQL) reads/writes with local YAML files so the tool
runs with no metadata database. Each logical table is one YAML file under the
configured registry_dir, holding a list of row dicts.
"""
import os
import pathlib

import yaml


def _config_path():
    override = os.environ.get("DE_CONFIG_PATH")
    if override:
        return pathlib.Path(override)
    for parent in pathlib.Path(__file__).resolve().parents:
        if (parent / "config.yml").exists():
            return parent / "config.yml"
    raise FileNotFoundError("config.yml not found; set DE_CONFIG_PATH")


def _config():
    with open(_config_path()) as handle:
        return yaml.safe_load(handle) or {}


def backend_mode():
    return (_config().get("backend") or {}).get("mode") or "datalake_config"


def _registry_dir():
    cfg = _config()
    rel = (cfg.get("backend") or {}).get("registry_dir", "registry")
    directory = _config_path().resolve().parent / rel
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_table(name):
    path = _registry_dir() / f"{name}.yml"
    if not path.exists():
        return []
    with open(path) as handle:
        return yaml.safe_load(handle) or []


def save_table(name, rows):
    with open(_registry_dir() / f"{name}.yml", "w") as handle:
        yaml.safe_dump(rows, handle, sort_keys=False)


def find(name, **match):
    for row in load_table(name):
        if all(row.get(k) == v for k, v in match.items()):
            return row
    return None


def find_all(name, **match):
    return [r for r in load_table(name) if all(r.get(k) == v for k, v in match.items())]


def insert(name, row):
    rows = load_table(name)
    rows.append(row)
    save_table(name, rows)


def update(name, match, changes):
    rows = load_table(name)
    count = 0
    for row in rows:
        if all(row.get(k) == v for k, v in match.items()):
            row.update(changes)
            count += 1
    save_table(name, rows)
    return count

import os
import pathlib
import requests
import json
import time
from typing import Dict, Optional

import yaml


def _vault_base_url(env: str) -> Optional[str]:
    path = os.environ.get("DE_CONFIG_PATH")
    if not path:
        for parent in pathlib.Path(__file__).resolve().parents:
            if (parent / "config.yml").exists():
                path = parent / "config.yml"
                break
    with open(path) as handle:
        cfg = yaml.safe_load(handle) or {}
    return (cfg.get("vault") or {}).get(f"{env}_base_url")


def get_vault_credentials(vault_key: str, env: str) -> Optional[Dict]:
    """
    Retrieve credentials from HashiCorp Vault.
    
    Args:
        vault_key: The vault key path
        env: Environment (stage/prod)
    
    Returns:
        Dict containing vault data or None if failed
    """
    if env == "stage":
        vault_base_url = _vault_base_url("stage")
        vault_token = os.environ.get("VAULT_STAGE_TOKEN")
    elif env == "prod":
        vault_base_url = _vault_base_url("prod")
        vault_token = os.environ.get("VAULT_PROD_TOKEN")
    else:
        print(f"❌ ERROR: Invalid environment '{env}'. Must be 'stage' or 'prod'")
        return None

    if not vault_token:
        print(f"❌ ERROR: Vault token not found for environment '{env}'")
        return None

    vault_url = f"{vault_base_url}/v1/kv/data/{env}/{vault_key}"
    headers = {"Authorization": f"Bearer {vault_token}"}
    
    max_retries = 5
    retry_interval = 2
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔑 Attempting to retrieve vault credentials (attempt {attempt}/{max_retries})")
            response = requests.get(url=vault_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            time.sleep(2)

            response_object = {"status_code": response.status_code, "data": response.content}
            
            return json.loads(response_object["data"])["data"]["data"]
            
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Vault request attempt {attempt} failed: {str(e)}")
            if attempt < max_retries:
                time.sleep(retry_interval)
                retry_interval *= 2  # Exponential backoff
            continue
    
    print(f"❌ ERROR: Failed to retrieve vault credentials after {max_retries} attempts")
    return None

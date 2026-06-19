import boto3
import requests
import logging
import os
from typing import Optional, Tuple
from airflow.models import Variable
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


def _load_config():
    import pathlib
    import yaml
    path = os.environ.get("DE_CONFIG_PATH")
    if not path:
        for parent in pathlib.Path(__file__).resolve().parents:
            if (parent / "config.yml").exists():
                path = parent / "config.yml"
                break
    with open(path) as handle:
        return yaml.safe_load(handle) or {}


_CFG = _load_config()


class MWAASessionManager:
    MWAA_ENV_NAME = _CFG["airflow"]["prod_env_name"]
    MWAA_REGION = _CFG["aws"]["region"]

    VARIABLE_KEY = "mwaa_session_jwt_token"
    VARIABLE_HOSTNAME_KEY = "mwaa_session_hostname"

    def __init__(self):
        self._hostname = None
        self._jwt_token = None

    def _create_session(self) -> Tuple[str, str]:
        logger.info("Creating new MWAA session")
        # Use credentials from pipeline environment variables
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID_PROD")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY_PROD")
        aws_session_token = os.getenv("AWS_SESSION_TOKEN_PROD")
        
        mwaa = boto3.client(
            "mwaa",
            region_name=self.MWAA_REGION,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
        )

        resp = mwaa.create_web_login_token(Name=self.MWAA_ENV_NAME)

        hostname = resp["WebServerHostname"]
        web_token = resp["WebToken"]

        login = requests.post(
            f"https://{hostname}/pluginsv2/aws_mwaa/login",
            data={"token": web_token},
            timeout=10,
        )
        login.raise_for_status()

        jwt_token = login.cookies["_token"]

        try:
            Variable.set(self.VARIABLE_KEY, jwt_token)
            Variable.set(self.VARIABLE_HOSTNAME_KEY, hostname)
        except Exception as e:
            logger.warning("Failed to cache session: %s", e)

        self._hostname = hostname
        self._jwt_token = jwt_token

        return hostname, jwt_token

    def _load_cached_session(self) -> Optional[Tuple[str, str]]:
        if self._hostname and self._jwt_token:
            return self._hostname, self._jwt_token

        try:
            jwt_token = Variable.get(self.VARIABLE_KEY, default_var=None)
            hostname = Variable.get(self.VARIABLE_HOSTNAME_KEY, default_var=None)

            if jwt_token and hostname:
                self._hostname = hostname
                self._jwt_token = jwt_token
                return hostname, jwt_token
        except Exception as e:
            logger.warning("Failed to load cached session: %s", e)

        return None

    def _get_headers(self, jwt_token: str):
        return {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type(
            (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException,
            )
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _make_request(self, method: str, url: str, headers: dict, **kwargs) -> requests.Response:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs,
        )

        if 500 <= response.status_code < 600:
            logger.warning("Server error %s for %s", response.status_code, url)
            response.raise_for_status()

        return response

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        cached = self._load_cached_session()
        hostname, jwt_token = cached if cached else self._create_session()

        url = f"https://{hostname}/api/v2{path}"

        response = self._make_request(
            method,
            url,
            headers=self._get_headers(jwt_token),
            **kwargs,
        )

        if response.status_code == 401:
            logger.warning("Session expired. Refreshing...")

            hostname, jwt_token = self._create_session()

            response = self._make_request(
                method,
                f"https://{hostname}/api/v2{path}",
                headers=self._get_headers(jwt_token),
                **kwargs,
            )

        response.raise_for_status()
        return response


mwaa_session = MWAASessionManager()
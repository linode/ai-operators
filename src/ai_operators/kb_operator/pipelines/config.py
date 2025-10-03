import base64
import json
import logging
import os
import enum
from json import JSONDecodeError
from typing import Iterable

from attrs import define
from cattrs import BaseValidationError

from ai_operators.ml_operator.converter import converter

from kubernetes_asyncio.client import (
    ApiException,
    CoreV1Api,
)
from kubernetes_asyncio.client.api_client import ApiClient

logger = logging.getLogger(__name__)


class PipelineSourceAuth(enum.StrEnum):
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"


@define
class PipelineSourceConfig:
    """
    Represents a pipeline source configuration as used within the operator.
    """

    url: str
    version: str | None = None
    auth_type: PipelineSourceAuth = PipelineSourceAuth.NONE
    auth_token: str = None


@define
class StoredPipelineSourceConfig:
    """
    Represents a pipeline source configuration as stored in the ConfigMap.
    """

    url: str
    version: str | None = None
    auth_type: PipelineSourceAuth = PipelineSourceAuth.NONE
    auth_secret_name: str | None = None
    auth_secret_key: str | None = None

    @classmethod
    def from_dict(cls, input: dict[str, str]) -> "StoredPipelineSourceConfig":
        return converter.structure(input, cls)


CONFIG_MAP_NAME = "pipelines"


class PipelineConfigLoader:
    """
    Loads pipeline source configurations from a ConfigMap.
    """

    def __init__(self):
        self._namespace = os.getenv("NAMESPACE") or "ml-operator"
        self._current_config: dict[str, PipelineSourceConfig] = {}

    async def _load_config(self) -> dict[str, str]:
        async with ApiClient() as api:
            core_api = CoreV1Api(api)
            try:
                configmap = await core_api.read_namespaced_config_map(
                    "pipelines", self._namespace
                )  # type: V1ConfigMap
            except ApiException as e:
                if e.status == 404:
                    logger.info("No pipeline configuration set.")
                    return {}
        return configmap.data or {}

    async def _load_secrets(
        self, secret_names: Iterable[str]
    ) -> dict[str, dict[str, str]]:
        secrets = {}  # type: dict[str, dict[str, str]]
        async with ApiClient() as api:
            core_api = CoreV1Api(api)
            for secret_name in secret_names:
                try:
                    secret = await core_api.read_namespaced_secret(
                        secret_name,
                        self._namespace,
                    )  # type: V1Secret
                    secret_data = {
                        key: base64.b64decode(value).decode()
                        for key, value in secret.data.items()
                    }
                except ApiException:
                    # Missing secrets are handled later
                    pass
                else:
                    secrets[secret_name] = secret_data
        return secrets

    async def _update_config_items(
        self, updated_configs: dict[str, StoredPipelineSourceConfig]
    ) -> None:
        secret_names = {
            stored_config.auth_secret_name
            for stored_config in updated_configs.values()
            if stored_config.auth_type != PipelineSourceAuth.NONE
            and stored_config.auth_secret_name
        }
        secrets = await self._load_secrets(secret_names)
        for name, stored_config in updated_configs.items():
            if stored_config.auth_type == PipelineSourceAuth.NONE:
                self._current_config[name] = PipelineSourceConfig(
                    stored_config.url,
                    stored_config.version,
                    stored_config.auth_type,
                )
            else:
                if stored_config.auth_secret_name and stored_config.auth_secret_key:
                    secret = secrets.get(stored_config.auth_secret_name)
                    if secret:
                        secret_value = secret.get(stored_config.auth_secret_key)
                        if secret_value:
                            self._current_config[name] = PipelineSourceConfig(
                                stored_config.url,
                                stored_config.version,
                                stored_config.auth_type,
                                secret_value,
                            )
                        else:
                            logger.error(
                                f"Secret key '{stored_config.auth_secret_key}' not found in '{stored_config.auth_secret_name}' for config '{name}'."
                            )
                    else:
                        logger.error(
                            f"Secret '{stored_config.auth_secret_name}' not available for config '{name}'."
                        )
                else:
                    logger.error(
                        f"Pipeline configuration '{name}' is configured to use authentication, but secret was not provided or is not available."
                    )

    async def update_config(self):
        """
        Updates the configuration from the ConfigMap in the cluster.
        """
        loaded_config = await self._load_config()
        logger.info(
            f"Processing {len(loaded_config.keys())} pipeline source configurations."
        )
        updated_configs = {}  # type: dict[str, StoredPipelineSourceConfig]
        for name, config_str in loaded_config.items():
            try:
                config_dict = json.loads(config_str)
                stored_config = StoredPipelineSourceConfig.from_dict(config_dict)
            except (BaseValidationError, JSONDecodeError, KeyError) as e:
                logger.error(
                    f"Invalid pipeline configuration for '{name}'.", exc_info=e
                )
            else:
                updated_configs[name] = stored_config
        await self._update_config_items(updated_configs)
        discarded_names = set(self._current_config.keys()) - set(loaded_config.keys())
        for name in discarded_names:
            del self._current_config[name]

    @property
    def config(self) -> dict[str, PipelineSourceConfig]:
        """
        Returns the last set of configurations retrieved.
        """
        return self._current_config

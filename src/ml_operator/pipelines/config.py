import logging
import os
from typing import Any

from attrs import define
from cattrs import BaseValidationError

from ..converter import converter

from kubernetes_asyncio.client import (
    ApiException,
    CoreV1Api,
    V1ConfigMap,
)
from kubernetes_asyncio.client.api_client import ApiClient

logger = logging.getLogger(__name__)


@define
class PipelineRepoConfig:
    url: str
    ref: str | None = None

    @classmethod
    def from_dict(cls, input: dict[str, str]) -> "PipelineRepoConfig":
        return converter.structure(input, cls)


CONFIG_MAP_NAME = "pipelines"


class PipelineConfigLoader:
    """
    Loads pipeline repository configurations from a ConfigMap.
    """

    def __init__(self):
        self._namespace = os.getenv("NAMESPACE") or "ml-operator"
        self._current_config: dict[str, PipelineRepoConfig] = {}

    async def _load_config(self) -> dict[str, Any]:
        async with ApiClient() as api:
            core_api = CoreV1Api(api)
            try:
                configmap: V1ConfigMap = core_api.read_namespaced_config_map(
                    "pipelines", self._namespace
                )
            except ApiException as e:
                if e.status == 404:
                    logger.info("No pipeline configuration set.")
                    return {}
        return configmap.data.get("repositories") or {}

    async def update_config(self):
        """
        Updates the configuration from the ConfigMap in the cluster.
        """
        loaded_config = await self._load_config()
        for name, config_dict in loaded_config.items():
            try:
                config = PipelineRepoConfig.from_dict(config_dict)
            except (BaseValidationError, KeyError) as e:
                logger.warning(f"Invalid pipeline configuration for '{name}'.")
                logger.error(e)
            else:
                self._current_config[name] = config
        discarded_names = set(self._current_config.keys()) - set(loaded_config.keys())
        for name in discarded_names:
            del self._current_config[name]

    def get_config(self) -> dict[str, PipelineRepoConfig]:
        """
        Returns the last set of configurations retrieved.
        """
        return self._current_config

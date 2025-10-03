import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from kubernetes_asyncio import client
from kubernetes_asyncio.client import ApiException

from ..constants import CUSTOM_API_ARGS


class StatusService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._custom_api: Optional[client.CustomObjectsApi] = None

    async def _get_custom_api(self) -> client.CustomObjectsApi:
        if not self._custom_api:
            async with client.ApiClient() as api_client:
                self._custom_api = client.CustomObjectsApi(api_client)
        return self._custom_api

    async def _update_agent_status(
        self, namespace: str, name: str, status_update: Dict[str, Any]
    ) -> None:
        try:
            custom_api = await self._get_custom_api()

            # Add timestamp to status update
            status_update["lastUpdated"] = datetime.now(timezone.utc).isoformat()

            # Update the status subresource
            await custom_api.patch_namespaced_custom_object_status(
                group=CUSTOM_API_ARGS["group"],
                version=CUSTOM_API_ARGS["version"],
                namespace=namespace,
                plural=CUSTOM_API_ARGS["plural"],
                name=name,
                body={"status": status_update},
            )
            self.logger.info(
                f"Updated status for AkamaiAgent {name} in namespace {namespace}"
            )

        except ApiException as e:
            self.logger.error(f"Failed to update status for AkamaiAgent {name}: {e}")
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error updating status for AkamaiAgent {name}: {e}"
            )
            raise

    async def set_agent_deployed(
        self, namespace: str, name: str, deployment_id: str
    ) -> None:
        self.logger.info(
            f"Setting agent {name} status to deployed with deployment_id: {deployment_id}"
        )
        await self._update_agent_status(
            namespace,
            name,
            {
                "phase": "Deployed",
                "deploymentId": deployment_id,
                "message": "Agent successfully deployed",
            },
        )

    async def clear_agent_failed(self, namespace: str, name: str) -> None:
        self.logger.info(f"Clearing failed status for agent {name}")
        await self._update_agent_status(
            namespace,
            name,
            {"phase": "Deployed", "message": "Agent deployment recovered"},
        )

    async def set_agent_failed(self, namespace: str, name: str, error: str) -> None:
        self.logger.error(f"Setting agent {name} status to failed: {error}")
        await self._update_agent_status(
            namespace,
            name,
            {
                "phase": "Failed",
                "message": f"Agent deployment failed: {error}",
                "error": error,
            },
        )

    async def set_knowledge_base_linked(
        self, namespace: str, name: str, kb_name: str
    ) -> None:
        self.logger.info(f"Setting knowledge base {kb_name} as linked for agent {name}")
        await self._update_agent_status(
            namespace, name, {"knowledgeBase": {"name": kb_name, "status": "Linked"}}
        )

    async def set_knowledge_base_error(
        self, namespace: str, name: str, error: str
    ) -> None:
        self.logger.error(f"Setting knowledge base error for agent {name}: {error}")
        await self._update_agent_status(
            namespace,
            name,
            {
                "phase": "Failed",
                "knowledgeBase": {"status": "Error", "error": error},
                "message": f"Knowledge base error: {error}",
                "error": error,
            },
        )

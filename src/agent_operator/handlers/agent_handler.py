import logging
from typing import Dict, Any, Optional

from ..resource import AkamaiAgent
from ..constants import PROVIDER
from ..services.agent_data import create_agent_data
from ..services.argocd_service import ArgoCDDeployer
from ..services.helm_service import K8sDeploymentService
from ..services.status_service import StatusService


class AgentHandler:
    """
    Handles AkamaiAgent CR lifecycle events (create, update, delete).

    Uses duck typing to delegate deployment operations to either ArgoCDDeploymentService
    or HelmDeploymentService based on the PROVIDER environment variable. Both services
    implement the same interface (create_agent, update_agent, delete_agent,
    get_deployment_status) without requiring explicit protocol inheritance.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if PROVIDER == "apl":
            self.agent_service = ArgoCDDeployer()
        else:
            self.agent_service = K8sDeploymentService()
        self.status_service = StatusService()

    async def created(self, namespace: str, name: str, agent: AkamaiAgent):
        self.logger.info(f"Processing created agent {name} in namespace {namespace}")

        try:
            agent_data = await create_agent_data(namespace, name, agent)

            status = await self.agent_service.get_deployment_status(agent_data)
            if status:
                self.logger.info(
                    f"Agent {name} deployment already exists, skipping creation"
                )
                await self.status_service.set_agent_deployed(namespace, name, name)
                return

            deployment_id = await self.agent_service.create_agent(agent_data)
            await self.status_service.set_agent_deployed(namespace, name, deployment_id)
            await self.status_service.clear_agent_failed(namespace, name)

            self.logger.info(
                f"Agent {name} created successfully with model {agent.foundation_model} (deployment: {deployment_id})"
            )

        except Exception as e:
            self.logger.error(f"Failed to create agent {name}: {e}")
            if "Knowledge base" in str(e):
                await self.status_service.set_knowledge_base_error(
                    namespace, name, str(e)
                )
            else:
                await self.status_service.set_agent_failed(namespace, name, str(e))
            raise

    async def updated(self, namespace: str, name: str, agent: AkamaiAgent):
        self.logger.info(f"Processing updated agent {name} in namespace {namespace}")

        try:
            agent_data = await create_agent_data(namespace, name, agent)
            deployment_id = await self.agent_service.update_agent(agent_data)
            await self.status_service.set_agent_deployed(namespace, name, deployment_id)
            await self.status_service.clear_agent_failed(namespace, name)

            self.logger.info(
                f"Agent {name} updated successfully (deployment: {deployment_id})"
            )

        except Exception as e:
            self.logger.error(f"Failed to update agent {name}: {e}")
            if "Knowledge base" in str(e):
                await self.status_service.set_knowledge_base_error(
                    namespace, name, str(e)
                )
            else:
                await self.status_service.set_agent_failed(namespace, name, str(e))
            raise

    async def deleted(self, namespace: str, name: str, agent: AkamaiAgent):
        self.logger.info(
            f"Processing deletion of agent {name} in namespace {namespace}"
        )

        try:
            agent_data = await create_agent_data(namespace, name, agent)
            await self.agent_service.delete_agent(agent_data)
            self.logger.info(f"Agent {name} cleanup completed")
        except Exception as e:
            self.logger.error(f"Failed to delete agent {name}: {e}")
            raise

    async def get_agent_status(
        self, namespace: str, name: str, agent: AkamaiAgent
    ) -> Optional[Dict[str, Any]]:
        try:
            agent_data = await create_agent_data(namespace, name, agent)
            return await self.agent_service.get_deployment_status(agent_data)
        except Exception as e:
            self.logger.error(f"Failed to get status for agent {name}: {e}")
            return None

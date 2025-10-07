import logging

from ai_operators.agent_operator.constants import PROVIDER
from ai_operators.agent_operator.model.agent_data import create_agent_data, AgentData
from ai_operators.agent_operator.resource import AkamaiAgent
from ai_operators.agent_operator.services.argocd_deployer import ArgoCDDeployer
from ai_operators.agent_operator.services.k8s_deployer import K8sDeployer
from ai_operators.agent_operator.utils.status import (
    get_agent_deployed_status,
)


class AgentHandler:
    """
    Handles AkamaiAgent CR lifecycle events (create, update, delete).

    Uses duck typing to delegate deployment operations to either ArgoCDDeployer
    or K8sDeployer based on the PROVIDER environment variable. Both services
    implement the same interface (create_agent, update_agent, delete_agent,
    get_deployment_status).
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if PROVIDER == "apl":
            self.agent_service = ArgoCDDeployer()
        else:
            self.agent_service = K8sDeployer()

    async def created(self, namespace: str, name: str, agent: AkamaiAgent):
        self.logger.info(f"Processing created agent {name} in namespace {namespace}")

        try:
            agent_data = await create_agent_data(namespace, name, agent)

            deployment_status = await self.agent_service.get_deployment_status(
                agent_data
            )
            if deployment_status:
                self.logger.info(
                    f"Agent {name} deployment already exists, skipping creation"
                )
                return get_agent_deployed_status(name).to_dict()

            deployment_id = await self.agent_service.create_agent(agent_data)

            self.logger.info(
                f"Agent {name} created successfully with model {agent.foundation_model} (deployment: {deployment_id})"
            )

            return get_agent_deployed_status(name).to_dict()

        except Exception as e:
            self.logger.error(f"Failed to create agent {name}: {e}")
            raise

    async def updated(self, namespace: str, name: str, agent: AkamaiAgent):
        self.logger.info(f"Processing updated agent {name} in namespace {namespace}")

        try:
            agent_data = await create_agent_data(namespace, name, agent)
            deployment_id = await self.agent_service.update_agent(agent_data)

            self.logger.info(
                f"Agent {name} updated successfully (deployment: {deployment_id})"
            )

            return get_agent_deployed_status(name).to_dict()

        except Exception as e:
            self.logger.error(f"Failed to update agent {name}: {e}")
            raise

    async def deleted(self, namespace: str, name: str, agent: AkamaiAgent):
        self.logger.info(
            f"Processing deletion of agent {name} in namespace {namespace}"
        )

        try:
            # For deletion, we don't need full agent data with enriched KB configs
            # Create minimal AgentData with basic info
            agent_data = AgentData(
                namespace=namespace,
                name=name,
                foundation_model=agent.foundation_model,
                foundation_model_endpoint="",  # Not needed for deletion
                system_prompt=agent.system_prompt,
                routes=[],
                tools=[],
            )
            await self.agent_service.delete_agent(agent_data)
            self.logger.info(f"Agent {name} cleanup completed")
        except Exception as e:
            self.logger.error(f"Failed to delete agent {name}: {e}")
            raise

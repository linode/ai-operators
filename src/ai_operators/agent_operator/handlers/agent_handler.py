import logging

from ai_operators.agent_operator.constants import PROVIDER
from ai_operators.agent_operator.model.agent_data import create_agent_data, AgentData
from ai_operators.agent_operator.resource import AkamaiAgent
from ai_operators.agent_operator.services.argocd_deployer import ArgoCDDeployer
from ai_operators.agent_operator.services.k8s_deployer import K8sDeployer
from ai_operators.agent_operator.utils.k8s import wait_for_deployment_ready
from ai_operators.agent_operator.utils.status import (
    get_agent_running_status,
    get_agent_deployed_not_ready_status,
    get_agent_failed_status,
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
            existing_status = await self.wait_for_agent_ready(namespace, name)
            if existing_status:
                self.logger.info(
                    f"Agent {name} deployment already exists, returning current status"
                )
                return existing_status

            agent_data = await create_agent_data(namespace, name, agent)
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
            agent_data = AgentData.for_deletion(namespace, name, agent)
            await self.agent_service.delete_agent(agent_data)
            self.logger.info(f"Agent {name} cleanup completed")
        except Exception as e:
            self.logger.error(f"Failed to delete agent {name}: {e}")
            raise

    async def wait_for_agent_ready(self, namespace: str, name: str):
        """
        Wait for agent deployment to become ready and return appropriate status.

        This checks if the deployment exists and waits for it to become ready.
        Returns appropriate status dict based on deployment state:
        - Running: if deployment exists and pods are ready
        - Deployed (not ready): if deployment exists but pods aren't ready within timeout
        - None: if deployment doesn't exist

        Can be used for:
        - Checking existing deployments (e.g., during create when deployment already exists)
        - Waiting for newly created/updated deployments to become ready
        """
        import asyncio
        from kubernetes_asyncio import client
        from kubernetes_asyncio.client import ApiException

        agent_data = AgentData.for_status_check(namespace, name)

        # Wait for Kubernetes deployment to exist (with timeout)
        deployment_wait_timeout = 120  # seconds to wait for deployment to be created
        deployment_poll_interval = 2  # seconds between checks
        elapsed = 0
        deployment_exists = False

        while elapsed < deployment_wait_timeout:
            try:
                async with client.ApiClient() as api_client:
                    apps_api = client.AppsV1Api(api_client)
                    await apps_api.read_namespaced_deployment(
                        name=agent_data.name, namespace=agent_data.namespace
                    )
                    deployment_exists = True
                    break
            except ApiException as e:
                if e.status != 404:
                    self.logger.error(f"Error checking deployment {name}: {e}")

            await asyncio.sleep(deployment_poll_interval)
            elapsed += deployment_poll_interval

        if not deployment_exists:
            self.logger.warning(
                f"Deployment {name} not found after {deployment_wait_timeout}s"
            )
            return None

        self.logger.info(f"Waiting for agent {name} to become ready")
        is_ready = await wait_for_deployment_ready(
            name=agent_data.name,
            namespace=agent_data.namespace,
            timeout=420,
            poll_interval=5,
        )

        if is_ready:
            return get_agent_running_status(name).to_dict()
        else:
            return get_agent_deployed_not_ready_status(
                name, "Pods not ready within timeout"
            ).to_dict()

    def mark_failed(self, reason: str, error_message: str):
        """
        Create a failed status for an agent.

        Called by Kopf error handlers after all retries are exhausted.
        Returns the status dict that Kopf will automatically store.
        """
        self.logger.error(f"Agent deployment failed: {reason} - {error_message}")
        return get_agent_failed_status(reason, error_message).to_dict()

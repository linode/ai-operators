import os
import logging
import subprocess
from typing import Dict, Any, Optional

from kubernetes_asyncio import client
from kubernetes_asyncio.client import ApiException

from ai_operators.agent_operator.model.agent_data import AgentData
from ai_operators.agent_operator.utils.helm import (
    create_helm_values,
    template_agent_chart,
)


class K8sDeployer:
    """Service to manage kubectl-based deployment of agents."""

    def __init__(self, manifest_dir: str = "/tmp/agent-manifests"):
        self.logger = logging.getLogger(__name__)
        self.manifest_dir = manifest_dir

        # Create manifest directory if it doesn't exist
        os.makedirs(self.manifest_dir, exist_ok=True)
        self.logger.info(
            f"K8sDeployer initialized with manifest directory: {self.manifest_dir}"
        )

    def _get_manifest_dir(self, agent_name: str) -> str:
        return os.path.join("/tmp/agents", agent_name)

    def _apply_manifest_dir(self, manifest_dir: str, namespace: str) -> None:
        """Apply manifests from a directory using kubectl."""
        try:
            cmd = [
                "kubectl",
                "apply",
                "-f",
                manifest_dir,
                "-n",
                namespace,
                "--recursive",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.info(
                f"Successfully applied manifests from {manifest_dir}: {result.stdout.strip()}"
            )

        except subprocess.CalledProcessError as e:
            self.logger.error(f"kubectl apply failed for {manifest_dir}: {e.stderr}")
            raise

    def _delete_manifest_dir(self, manifest_dir: str, namespace: str) -> None:
        """Delete resources from a manifest directory using kubectl."""
        try:
            cmd = [
                "kubectl",
                "delete",
                "-f",
                manifest_dir,
                "-n",
                namespace,
                "--recursive",
                "--ignore-not-found=true",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.info(
                f"Successfully deleted resources from {manifest_dir}: {result.stdout.strip()}"
            )

        except subprocess.CalledProcessError as e:
            self.logger.error(f"kubectl delete failed for {manifest_dir}: {e.stderr}")
            raise

    async def create_agent(self, agent_data: AgentData) -> str:
        """Deploy agent using Helm chart templating and kubectl apply."""

        self.logger.info(
            f"Deploying agent {agent_data.name} to namespace {agent_data.namespace}"
        )

        values = create_helm_values(agent_data)
        manifest_dir = template_agent_chart(
            agent_name=agent_data.name,
            namespace=agent_data.namespace,
            values=values,
            output_dir=self.manifest_dir,
        )

        self._apply_manifest_dir(manifest_dir, agent_data.namespace)

        self.logger.info(f"Successfully deployed agent {agent_data.name}")
        return agent_data.name

    async def update_agent(self, agent_data: AgentData) -> str:
        """Update existing agent deployment."""
        # kubectl apply handles both create and update
        return await self.create_agent(agent_data)

    async def delete_agent(self, agent_data: AgentData) -> None:
        """Delete agent deployment and related resources using kubectl."""
        manifest_dir = self._get_manifest_dir(agent_data.name)

        # If manifest doesn't exist, template it first
        if not os.path.exists(manifest_dir):
            self.logger.info(
                f"Manifest directory not found for agent {agent_data.name}, templating chart for deletion"
            )

            values = create_helm_values(agent_data)
            manifest_dir = template_agent_chart(
                agent_name=agent_data.name,
                namespace=agent_data.namespace,
                values=values,
                output_dir=self.manifest_dir,
            )

        self.logger.info(
            f"Deleting agent {agent_data.name} from namespace {agent_data.namespace}"
        )

        self._delete_manifest_dir(manifest_dir, agent_data.namespace)

        self.logger.info(f"Successfully deleted agent {agent_data.name}")

    # TODO make this strongly typed
    async def get_deployment_status(
        self, agent_data: AgentData
    ) -> Optional[Dict[str, Any]]:
        """Get the status of an agent deployment."""
        try:
            async with client.ApiClient() as api_client:
                apps_api = client.AppsV1Api(api_client)
                deployment = await apps_api.read_namespaced_deployment(
                    name=agent_data.name, namespace=agent_data.namespace
                )
                return deployment.status.to_dict()

        except ApiException as e:
            if e.status == 404:
                self.logger.debug(
                    f"Deployment {agent_data.name} not found in namespace {agent_data.namespace}"
                )
                return None
            else:
                self.logger.error(
                    f"Failed to get deployment status {agent_data.name}: {e}"
                )
                raise

import os
import logging
import subprocess
from typing import Dict, Any, Optional

from kubernetes_asyncio.client import ApiException

from .agent_data import AgentData
from .helm_utils import create_helm_values, template_agent_chart
from .k8s import get_apps_v1_api


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

    def _get_manifest_path(self, agent_name: str) -> str:
        return os.path.join(self.manifest_dir, f"{agent_name}.yaml")

    def _apply_manifest(self, manifest_file: str, namespace: str) -> None:
        """Apply a single manifest file using kubectl."""
        try:
            cmd = ["kubectl", "apply", "-f", manifest_file, "-n", namespace]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.info(
                f"Successfully applied manifest {manifest_file}: {result.stdout.strip()}"
            )

        except subprocess.CalledProcessError as e:
            self.logger.error(f"kubectl apply failed for {manifest_file}: {e.stderr}")
            raise

    def _delete_manifest(self, manifest_file: str, namespace: str) -> None:
        """Delete resources from a manifest file using kubectl."""
        try:
            cmd = [
                "kubectl",
                "delete",
                "-f",
                manifest_file,
                "-n",
                namespace,
                "--ignore-not-found=true",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.info(
                f"Successfully deleted resources from {manifest_file}: {result.stdout.strip()}"
            )

        except subprocess.CalledProcessError as e:
            self.logger.error(f"kubectl delete failed for {manifest_file}: {e.stderr}")
            raise
        finally:
            # Clean up manifest file
            if os.path.exists(manifest_file):
                os.remove(manifest_file)
                self.logger.debug(f"Removed manifest file: {manifest_file}")

    async def create_agent(self, agent_data: AgentData) -> str:
        """Deploy agent using Helm chart templating and kubectl apply."""

        self.logger.info(
            f"Deploying agent {agent_data.name} to namespace {agent_data.namespace}"
        )

        values = create_helm_values(agent_data)
        manifest_file = template_agent_chart(
            agent_name=agent_data.name,
            namespace=agent_data.namespace,
            values=values,
            output_dir=self.manifest_dir,
        )

        self._apply_manifest(manifest_file, agent_data.namespace)

        self.logger.info(f"Successfully deployed agent {agent_data.name}")
        return f"agent-{agent_data.name}"

    async def update_agent(self, agent_data: AgentData) -> str:
        """Update existing agent deployment."""
        # kubectl apply handles both create and update
        return await self.create_agent(agent_data)

    async def delete_agent(self, agent_data: AgentData) -> None:
        """Delete agent deployment and related resources using kubectl."""
        manifest_file = self._get_manifest_path(agent_data.name)

        # If manifest doesn't exist, template it first
        if not os.path.exists(manifest_file):
            self.logger.info(
                f"Manifest file not found for agent {agent_data.name}, templating chart for deletion"
            )

            values = create_helm_values(agent_data)
            manifest_file = template_agent_chart(
                agent_name=agent_data.name,
                namespace=agent_data.namespace,
                values=values,
                output_dir=self.manifest_dir,
            )

        self.logger.info(
            f"Deleting agent {agent_data.name} from namespace {agent_data.namespace}"
        )

        self._delete_manifest(manifest_file, agent_data.namespace)

        self.logger.info(f"Successfully deleted agent {agent_data.name}")

    async def get_deployment_status(
        self, agent_data: AgentData
    ) -> Optional[Dict[str, Any]]:
        """Get the status of an agent deployment."""
        try:
            apps_api = await get_apps_v1_api()
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

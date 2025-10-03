import logging
import os
import yaml
from typing import Dict, Any, Optional

from kubernetes_asyncio.client import ApiException

from .agent_data import AgentData
from .argocd_templates import get_application_template
from .helm_utils import create_helm_values
from .k8s import (
    create_custom_object,
    get_custom_object,
    patch_custom_object,
    delete_custom_object,
)


ARGOCD_API_ARGS = {
    "group": "argoproj.io",
    "version": "v1alpha1",
    "namespace": "argocd",
    "plural": "applications",
}


class ArgoCDDeployer:
    """Service to manage ArgoCD applications for agent deployments."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _create_argocd_application(self, agent_data: AgentData) -> Dict[str, Any]:
        """Create ArgoCD Application CR definition."""
        helm_values = create_helm_values(agent_data)

        git_repo_url = os.getenv(
            "AGENT_CHART_REPO_URL", "https://github.com/linode/ai-operators.git"
        )
        git_target_revision = os.getenv("AGENT_CHART_REPO_REVISION", "main")
        chart_path = os.getenv("AGENT_CHART_PATH", "agent")
        app_name = f"agent-{agent_data.name}"

        return get_application_template(
            app_name=app_name,
            argocd_namespace=ARGOCD_API_ARGS["namespace"],
            target_namespace=agent_data.namespace,
            git_repo_url=git_repo_url,
            chart_path=chart_path,
            git_target_revision=git_target_revision,
            helm_values=yaml.dump(helm_values),
            api_group=ARGOCD_API_ARGS["group"],
            api_version=ARGOCD_API_ARGS["version"],
        )

    async def create_agent(self, agent_data: AgentData) -> str:
        """Create ArgoCD application for agent deployment."""
        application = self._create_argocd_application(agent_data)
        app_name = application["metadata"]["name"]

        try:
            await create_custom_object(
                group=ARGOCD_API_ARGS["group"],
                version=ARGOCD_API_ARGS["version"],
                namespace=ARGOCD_API_ARGS["namespace"],
                plural=ARGOCD_API_ARGS["plural"],
                body=application,
            )

            self.logger.info(
                f"Created ArgoCD application {app_name} for agent {agent_data.name}"
            )
            return app_name

        except ApiException as e:
            if e.status == 409:
                self.logger.info(
                    f"ArgoCD application {app_name} already exists, updating..."
                )
                return await self.update_agent(agent_data)
            else:
                self.logger.error(
                    f"Failed to create ArgoCD application {app_name}: {e}"
                )
                raise

    async def update_agent(self, agent_data: AgentData) -> str:
        """Update existing ArgoCD application for agent deployment."""
        application = self._create_argocd_application(agent_data)
        app_name = application["metadata"]["name"]

        try:
            await patch_custom_object(
                group=ARGOCD_API_ARGS["group"],
                version=ARGOCD_API_ARGS["version"],
                namespace=ARGOCD_API_ARGS["namespace"],
                plural=ARGOCD_API_ARGS["plural"],
                name=app_name,
                body=application,
            )

            self.logger.info(
                f"Updated ArgoCD application {app_name} for agent {agent_data.name}"
            )
            return app_name

        except ApiException as e:
            self.logger.error(f"Failed to update ArgoCD application {app_name}: {e}")
            raise

    async def delete_agent(self, agent_data: AgentData) -> None:
        """Delete ArgoCD application for agent."""
        app_name = f"agent-{agent_data.name}"

        try:
            await delete_custom_object(
                group=ARGOCD_API_ARGS["group"],
                version=ARGOCD_API_ARGS["version"],
                namespace=ARGOCD_API_ARGS["namespace"],
                plural=ARGOCD_API_ARGS["plural"],
                name=app_name,
            )

            self.logger.info(
                f"Deleted ArgoCD application {app_name} for agent {agent_data.name}"
            )

        except ApiException as e:
            if e.status == 404:
                self.logger.warning(
                    f"ArgoCD application {app_name} not found (already deleted)"
                )
            else:
                self.logger.error(
                    f"Failed to delete ArgoCD application {app_name}: {e}"
                )
                raise

    async def get_deployment_status(
        self, agent_data: AgentData
    ) -> Optional[Dict[str, Any]]:
        """Get the status of an ArgoCD application."""
        app_name = f"agent-{agent_data.name}"

        app = await get_custom_object(
            group=ARGOCD_API_ARGS["group"],
            version=ARGOCD_API_ARGS["version"],
            namespace=ARGOCD_API_ARGS["namespace"],
            plural=ARGOCD_API_ARGS["plural"],
            name=app_name,
        )

        if not app:
            self.logger.debug(f"ArgoCD application {app_name} not found")
            return None

        return app.get("status", {})

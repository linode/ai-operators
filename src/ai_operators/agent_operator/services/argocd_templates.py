from typing import Dict, Any


def get_application_template(
    app_name: str,
    argocd_namespace: str,
    target_namespace: str,
    git_repo_url: str,
    chart_path: str,
    git_target_revision: str,
    helm_values: str,
    api_group: str,
    api_version: str,
) -> Dict[str, Any]:
    """Get ArgoCD Application template with substituted values."""
    return {
        "apiVersion": f"{api_group}/{api_version}",
        "kind": "Application",
        "metadata": {
            "name": app_name,
            "namespace": argocd_namespace,
            "annotations": {
                "argocd.argoproj.io/compare-options": "ServerSideDiff=true,IncludeMutationWebhook=true",
            },
            "labels": {
                "app.kubernetes.io/name": app_name,
                "app.kubernetes.io/component": "agent",
                "app.kubernetes.io/managed-by": "agent-operator",
            },
        },
        "spec": {
            "project": "default",
            "source": {
                "repoURL": git_repo_url,
                "path": chart_path,
                "targetRevision": git_target_revision,
                "helm": {
                    "values": helm_values,
                },
            },
            "destination": {
                "server": "https://kubernetes.default.svc",
                "namespace": target_namespace,
            },
            "syncPolicy": {
                "automated": {
                    "prune": True,
                    "allowEmpty": False,
                    "selfHeal": True,
                },
                "syncOptions": ["ServerSideApply=true"],
            },
        },
    }

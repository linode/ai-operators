"""Kubernetes API helper functions."""

from typing import Dict, Any, Optional

from kubernetes_asyncio import client
from kubernetes_asyncio.client import ApiException

from ..constants import KB_CUSTOM_API_ARGS


# API client creation helpers
async def get_custom_objects_api() -> client.CustomObjectsApi:
    """Get Kubernetes Custom Objects API client."""
    async with client.ApiClient() as api_client:
        return client.CustomObjectsApi(api_client)


async def get_core_v1_api() -> client.CoreV1Api:
    """Get Kubernetes Core V1 API client."""
    async with client.ApiClient() as api_client:
        return client.CoreV1Api(api_client)


async def get_apps_v1_api() -> client.AppsV1Api:
    """Get Kubernetes Apps V1 API client."""
    async with client.ApiClient() as api_client:
        return client.AppsV1Api(api_client)


# Custom Resource operations
async def create_custom_object(
    group: str, version: str, namespace: str, plural: str, body: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a custom resource object."""
    custom_api = await get_custom_objects_api()
    return await custom_api.create_namespaced_custom_object(
        group=group, version=version, namespace=namespace, plural=plural, body=body
    )


async def get_custom_object(
    group: str, version: str, namespace: str, plural: str, name: str
) -> Optional[Dict[str, Any]]:
    """Get a custom resource object."""
    try:
        custom_api = await get_custom_objects_api()
        return await custom_api.get_namespaced_custom_object(
            group=group, version=version, namespace=namespace, plural=plural, name=name
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def patch_custom_object(
    group: str,
    version: str,
    namespace: str,
    plural: str,
    name: str,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    """Patch a custom resource object."""
    custom_api = await get_custom_objects_api()
    return await custom_api.patch_namespaced_custom_object(
        group=group,
        version=version,
        namespace=namespace,
        plural=plural,
        name=name,
        body=body,
    )


async def delete_custom_object(
    group: str, version: str, namespace: str, plural: str, name: str
) -> None:
    """Delete a custom resource object."""
    try:
        custom_api = await get_custom_objects_api()
        await custom_api.delete_namespaced_custom_object(
            group=group, version=version, namespace=namespace, plural=plural, name=name
        )
    except ApiException as e:
        if e.status != 404:
            raise


async def fetch_knowledge_base_config(namespace: str, kb_name: str) -> Dict[str, Any]:
    """Fetch knowledge base configuration from KnowledgeBase CR."""
    try:
        kb_cr = await get_custom_object(
            group=KB_CUSTOM_API_ARGS["group"],
            version=KB_CUSTOM_API_ARGS["version"],
            namespace=namespace,
            plural=KB_CUSTOM_API_ARGS["plural"],
            name=kb_name,
        )

        if not kb_cr:
            raise ValueError(
                f"Knowledge base '{kb_name}' not found in namespace '{namespace}'"
            )

        # Extract spec and return pipelineParameters as config
        spec = kb_cr.get("spec", {})
        pipeline_params = spec.get("pipelineParameters", {})

        # Return the pipeline parameters as the KB config
        # This allows flexible KB configurations
        return {
            "pipeline_name": spec.get("pipelineName"),
            **pipeline_params,  # Merge all pipeline parameters
        }

    except ValueError:
        raise
    except Exception:
        # Re-raise other errors
        raise


async def get_foundation_model_endpoint(model_name: str) -> str:
    """Discover foundation model endpoint by querying services with labels."""
    core_api = await get_core_v1_api()

    # Query all services with modelType and modelName labels
    label_selector = f"modelType,modelName={model_name}"
    services = await core_api.list_service_for_all_namespaces(
        label_selector=label_selector
    )

    if services.items:
        # Use the first matching service
        service = services.items[0]
        service_name = service.metadata.name
        service_namespace = service.metadata.namespace
        return f"{service_name}.{service_namespace}.svc.cluster.local"
    else:
        raise ValueError(
            f"Foundation model '{model_name}' not found. No service with labels modelType,modelName={model_name}"
        )

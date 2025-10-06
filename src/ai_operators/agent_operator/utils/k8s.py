"""Kubernetes API helper functions."""

from typing import Dict, Any, Optional

from kubernetes_asyncio import client
from kubernetes_asyncio.client import ApiException

from ai_operators.agent_operator.constants import KB_CUSTOM_API_ARGS
from ai_operators.agent_operator.resource import AkamaiKnowledgeBase


async def create_custom_object(
    group: str, version: str, namespace: str, plural: str, body: Dict[str, Any]
) -> Dict[str, Any]:
    async with client.ApiClient() as api_client:
        custom_api = client.CustomObjectsApi(api_client)
        return await custom_api.create_namespaced_custom_object(
            group=group, version=version, namespace=namespace, plural=plural, body=body
        )


async def get_custom_object(
    group: str, version: str, namespace: str, plural: str, name: str
) -> Optional[Dict[str, Any]]:
    try:
        async with client.ApiClient() as api_client:
            custom_api = client.CustomObjectsApi(api_client)
            return await custom_api.get_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name,
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
    async with client.ApiClient() as api_client:
        custom_api = client.CustomObjectsApi(api_client)
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
    try:
        async with client.ApiClient() as api_client:
            custom_api = client.CustomObjectsApi(api_client)
            await custom_api.delete_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name,
            )
    except ApiException as e:
        if e.status != 404:
            raise


async def fetch_knowledge_base_config(
    namespace: str, kb_name: str
) -> AkamaiKnowledgeBase:
    """Fetch knowledge base configuration from the cluster based on the kb name"""
    kb_cr_dict = await get_custom_object(
        group=KB_CUSTOM_API_ARGS["group"],
        version=KB_CUSTOM_API_ARGS["version"],
        namespace=namespace,
        plural=KB_CUSTOM_API_ARGS["plural"],
        name=kb_name,
    )

    if not kb_cr_dict:
        raise ValueError(
            f"Knowledge base '{kb_name}' not found in namespace '{namespace}'"
        )

    spec = kb_cr_dict.get("spec", {})
    return AkamaiKnowledgeBase.from_spec(spec)


async def get_foundation_model_endpoint(model_name: str) -> str:
    """Discover foundation model endpoint by querying services with labels modelType and modelName."""
    async with client.ApiClient() as api_client:
        core_api = client.CoreV1Api(api_client)

        # Query all services with modelType and modelName labels
        label_selector = f"modelType,modelName={model_name}"
        services = await core_api.list_service_for_all_namespaces(
            label_selector=label_selector
        )

        if services.items:
            service = services.items[0]
            service_name = service.metadata.name
            service_namespace = service.metadata.namespace
            return f"{service_name}.{service_namespace}.svc.cluster.local"
        else:
            raise ValueError(
                f"Foundation model '{model_name}' not found. No service with labels modelType,modelName={model_name}"
            )

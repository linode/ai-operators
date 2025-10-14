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
        # custom_api.api_client.set_default_header('Content-Type', 'application/json-patch+json')
        return await custom_api.patch_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            name=name,
            body=body,
            _content_type="application/merge-patch+json",
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

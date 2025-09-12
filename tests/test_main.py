import asyncio
import os
from asyncio import sleep
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from kopf.testing import KopfRunner
from kubernetes_asyncio import config as k8s_config
from kubernetes_asyncio.client import ApiException, CustomObjectsApi, ApiextensionsV1Api
from kubernetes_asyncio.client.api_client import ApiClient

from ml_operator.constants import CUSTOM_API_ARGS
from tests.common import SAMPLE_KB_OBJECT

_DIR = Path(__file__).parent
with open(_DIR / "sample-spec.yaml", "r") as f:
    _SPEC = yaml.safe_load(f)

# All tests in this module only run if env variable USE_CLUSTER is set
USE_CLUSTER = (var := os.getenv("USE_CLUSTER")) and var not in ("0", "false")
pytestmark = pytest.mark.skipif(
    not USE_CLUSTER, reason="Requires a Kubernetes cluster to be configured"
)


@pytest.fixture(scope="module")
def runner():
    """
    Kopf runner for operator tests. Must be used in a context, e.g.
    ```
    with runner:
       ... do things
    ```
    """
    return KopfRunner(["run", "-A", "-m", "ml_operator", "--verbose"])


@pytest.fixture(scope="module", autouse=True)
async def k8s():
    """
    Utility to set up a Kubernetes API client.
    """
    await k8s_config.load_config()


@pytest.fixture(scope="module")
async def crd(k8s):
    """
    Sets up the CRD in the cluster for tests.
    Note that it fails all dependent tests, if the CRD is not valid.
    """
    with open(_DIR / ".." / "chart/crds/crd.yaml", "r") as f:
        crd = yaml.safe_load(f)
    # Validate that CRD corresponds with code constants
    assert crd["spec"]["group"] == CUSTOM_API_ARGS["group"]
    assert crd["spec"]["names"]["plural"] == CUSTOM_API_ARGS["plural"]
    # Install CRD
    async with ApiClient() as api:
        ext_api = ApiextensionsV1Api(api)
        await ext_api.create_custom_resource_definition(crd)
        yield
        try:
            await ext_api.delete_custom_resource_definition(crd["metadata"]["name"])
        except ApiException as e:
            if e.status == 404:
                pass
            raise e


def create_sample_cr(name: str) -> dict[str, Any]:
    """
    Provides a static sample CR definition to use in the cluster.
    """
    return {
        "apiVersion": f"{CUSTOM_API_ARGS['group']}/{CUSTOM_API_ARGS['version']}",
        "kind": "AkamaiKnowledgeBase",
        "metadata": {
            "name": name,
        },
        "spec": deepcopy(_SPEC),
    }


@pytest.fixture
async def cleanup_crs():
    yield
    async with ApiClient() as api:
        custom_api = CustomObjectsApi(api)
        try:
            all_crs = await custom_api.list_custom_object_for_all_namespaces(
                group=CUSTOM_API_ARGS["group"],
                version=CUSTOM_API_ARGS["group"],
                resource_plural=CUSTOM_API_ARGS["plural"],
            )
        except ApiException as e:
            if e.status == 404:
                return
            raise e
        body = [{"op": "remove", "path": "/metadata/finalizers/0"}]
        names = [
            (resource["metadata"]["namespace"], resource["metadata"]["name"])
            for resource in all_crs
        ]
        patches = [
            custom_api.patch_namespaced_custom_object(
                **CUSTOM_API_ARGS, namespace=namespace, name=name, body=body
            )
            for namespace, name in names
        ]
        await asyncio.gather(*patches)
        deletions = [
            custom_api.delete_namespaced_custom_object(
                **CUSTOM_API_ARGS, namespace=namespace, name=name
            )
            for namespace, name in names
        ]
        await asyncio.gather(*deletions)


@patch("ml_operator.main.HANDLER.created")
async def test_creation(mock_create, crd: None, runner: KopfRunner, cleanup_crs: None):
    sample_cr = create_sample_cr("test")
    with runner:
        async with ApiClient() as api:
            custom_api = CustomObjectsApi(api)
            await custom_api.create_namespaced_custom_object(
                **CUSTOM_API_ARGS,
                namespace="team-demo",
                body=sample_cr,
            )
        await sleep(5)
    mock_create.assert_called_with("team-demo", "test", SAMPLE_KB_OBJECT)

    assert runner.exit_code == 0, runner.output
    assert runner.exception is None, runner.output

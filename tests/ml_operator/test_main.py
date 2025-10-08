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
from kubernetes_asyncio.client import (
    ApiException,
    CoreV1Api,
    CustomObjectsApi,
    ApiextensionsV1Api,
)
from kubernetes_asyncio.client.api_client import ApiClient

from ai_operators.ml_operator import CUSTOM_API_ARGS
from ai_operators.ml_operator import AkamaiKnowledgeBase
from tests.ml_operator.conftest import SAMPLE_KB_OBJECT, SAMPLE_KB_DICT

_DIR = Path(__file__).parent.parent

# All tests in this module only run if env variable USE_CLUSTER is set
#
# WARNING:
# Tests below modify resources on a running K8s cluster! The "crd" fixture
# will fail if the CRD already exists, otherwise all resources are also cleaned
# up after tests. Make sure you are on the right cluster before setting this
# environment variable!
#
USE_CLUSTER = (var := os.getenv("USE_CLUSTER")) and var not in ("0", "false")
pytestmark = pytest.mark.skipif(
    not USE_CLUSTER, reason="Requires a Kubernetes cluster to be configured"
)


@pytest.fixture
def runner():
    """
    Kopf runner for operator tests. Must be used in a context, e.g.
    ```
    with runner:
       ... do things
    ```
    """
    os.environ["WATCH_NAMESPACES"] = "ml-operator-test"
    return KopfRunner(["run", "-A", "-m", "ml_operator", "--verbose"])


@pytest.fixture(scope="module", autouse=True)
async def k8s():
    """
    Utility to set up a Kubernetes API client.
    """
    await k8s_config.load_config()


@pytest.fixture(scope="module")
async def namespaces(k8s):
    """
    Ensures test-related namespaces for the test exist. Does not clean up.
    """
    test_namespaces = ["ml-operator-test", "ml-operator-unrelated"]
    async with ApiClient() as api:
        core_api = CoreV1Api(api)
        namespaces = await core_api.list_namespace()
        namespace_names = {namespace.metadata.name for namespace in namespaces.items}
        await asyncio.gather(
            *[
                core_api.create_namespace(
                    {"kind": "Namespace", "metadata": {"name": name}}
                )
                for name in test_namespaces
                if name not in namespace_names
            ]
        )
    yield test_namespaces


@pytest.fixture(scope="module")
async def crd(k8s):
    """
    Sets up the CRD in the cluster for tests, and removes it after.
    Also drops all related CRs.
    Note that it fails all dependent tests, if the CRD is not valid.
    """
    with open(_DIR / "resources/kb-crd.yaml", "r") as f:
        crd = yaml.safe_load(f)
    # Validate that CRD corresponds with code constants
    assert crd["spec"]["group"] == CUSTOM_API_ARGS["group"]
    assert crd["spec"]["names"]["plural"] == CUSTOM_API_ARGS["plural"]
    # Install CRD
    async with ApiClient() as api:
        ext_api = ApiextensionsV1Api(api)
        await ext_api.create_custom_resource_definition(crd)
        yield

        custom_api = CustomObjectsApi(api)
        try:
            all_crs = await custom_api.list_custom_object_for_all_namespaces(
                group=CUSTOM_API_ARGS["group"],
                version=CUSTOM_API_ARGS["version"],
                resource_plural=CUSTOM_API_ARGS["plural"],
            )
        except ApiException as e:
            if e.status == 404:
                return
            raise e
        body = [{"op": "remove", "path": "/metadata/finalizers"}]
        names = [
            (resource["metadata"]["namespace"], resource["metadata"]["name"])
            for resource in all_crs["items"]
        ]
        patches = [
            custom_api.patch_namespaced_custom_object(
                **CUSTOM_API_ARGS, namespace=namespace, name=name, body=body
            )
            for namespace, name in names
        ]
        try:
            await asyncio.gather(*patches)
        except ApiException as e:
            if e.status != 422:
                raise e
        deletions = [
            custom_api.delete_namespaced_custom_object(
                **CUSTOM_API_ARGS, namespace=namespace, name=name
            )
            for namespace, name in names
        ]
        await asyncio.gather(*deletions)

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
        "spec": deepcopy(SAMPLE_KB_DICT),
    }


@patch("ml_operator.main.KB_HANDLER.wait_for_completion")
@patch("ml_operator.main.KB_HANDLER.created")
@patch("ml_operator.main.KB_HANDLER.updated")
@patch("ml_operator.main.KB_HANDLER.deleted")
async def test_lifecycle(
    mock_delete,
    mock_update,
    mock_create,
    mock_wait,
    crd: None,
    runner: KopfRunner,
    namespaces: list[str],
):
    sample_cr = create_sample_cr("lifecycle-test")
    with runner:
        for namespace in namespaces:
            expect_call = namespace != "ml-operator-unrelated"
            mock_create.reset_mock()
            mock_update.reset_mock()
            mock_delete.reset_mock()
            mock_wait.reset_mock()

            async with ApiClient() as api:
                custom_api = CustomObjectsApi(api)
                await custom_api.create_namespaced_custom_object(
                    **CUSTOM_API_ARGS,
                    namespace=namespace,
                    body=sample_cr,
                )
                await sleep(5)
                if expect_call:
                    mock_create.assert_called_once_with(
                        namespace, "lifecycle-test", SAMPLE_KB_OBJECT
                    )
                    mock_wait.assert_called()
                else:
                    mock_create.assert_not_called()

                await custom_api.patch_namespaced_custom_object(
                    **CUSTOM_API_ARGS,
                    namespace=namespace,
                    name="lifecycle-test",
                    body=[
                        {
                            "op": "replace",
                            "path": "/spec/pipelineParameters/embedding_model_name",
                            "value": "gpt-4",
                        }
                    ],
                )
                await sleep(5)
                updated_spec = deepcopy(SAMPLE_KB_DICT)
                updated_spec["pipelineParameters"]["embedding_model_name"] = "gpt-4"
                updated_kb = AkamaiKnowledgeBase.from_spec(updated_spec)
                if expect_call:
                    mock_update.assert_called_once_with(
                        namespace, "lifecycle-test", updated_kb
                    )
                    mock_wait.assert_called()
                else:
                    mock_update.assert_not_called()

                await custom_api.delete_namespaced_custom_object(
                    **CUSTOM_API_ARGS,
                    namespace=namespace,
                    name="lifecycle-test",
                )
                await sleep(5)
                if expect_call:
                    mock_delete.assert_called_once_with(
                        namespace, "lifecycle-test", updated_kb
                    )
                else:
                    mock_delete.assert_not_called()

    assert runner.exit_code == 0, runner.output
    assert runner.exception is None, runner.output

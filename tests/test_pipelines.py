import importlib
import sys
from io import BytesIO
from zipfile import ZipFile

from aiohttp import ClientResponseError
from aioresponses import aioresponses
from kfp.compiler import Compiler

from ml_operator.pipelines.downloader import (
    PipelineDownloader,
    PipelineDownloadConfig,
    PipelineFileResponse,
    SizeExceededException,
    UnexpectedResponseException,
)
import os
import tempfile
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
from kubernetes_asyncio.client import V1ConfigMap

from ml_operator.pipelines.config import PipelineConfigLoader, PipelineSourceConfig
from ml_operator.pipelines.updater import PipelineUpdater
from ml_operator.pipelines.uploader import PipelineUploader


async def test_config(mocker):
    """
    Reading the pipeline configuration from the cluster.
    """
    mock_core_api = mocker.patch(
        "ml_operator.pipelines.config.CoreV1Api.read_namespaced_config_map",
        return_value=V1ConfigMap(data={"default": {"url": "<test-url>"}}),
    )
    config_loader = PipelineConfigLoader()
    assert config_loader.get_config() == {}
    await config_loader.update_config()
    mock_core_api.assert_called_once_with("pipelines", "ml-operator")
    assert config_loader.get_config() == {
        "default": PipelineSourceConfig("<test-url>", None)
    }


@pytest.fixture
def temp_dir():
    """
    Provides a temporary directory per function.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as path:
        yield path


PIPELINE_SCRIPT = """\
from kfp import dsl

PIPELINE_FUNC_NAME = "test_pipeline"
PIPELINE_VERSION = "0.1.0"

@dsl.component(
    base_image='nvcr.io/nvidia/ai-workbench/python-cuda117:1.0.3',
    packages_to_install=['psycopg2-binary', 'llama-index', 'llama-index-vector-stores-postgres',
                         'llama-index-embeddings-openai-like', 'kubernetes']
)
def cmp():
    return "Hello!"

@dsl.pipeline(name='test-pipeline')
def test_pipeline():
    cmp()
"""


@pytest.fixture(scope="session")
def pipeline_script():
    """
    Provides a raw pipeline script for tests.
    """
    with NamedTemporaryFile("wt", suffix=".py", delete=False) as f:
        f.write(PIPELINE_SCRIPT)
    yield Path(f.name)
    try:
        os.unlink(f.name)
    except Exception:
        pass


@pytest.fixture(scope="session")
def compiled_pipeline(pipeline_script: Path):
    """
    Provides a compiled pipeline package.
    """
    mod_path = str(pipeline_script.parent)
    mod_name = pipeline_script.name.removesuffix(".py")
    sys.path.insert(0, mod_path)
    try:
        test_module = importlib.import_module(mod_name)
    finally:
        sys.path.remove(mod_path)
    with tempfile.TemporaryDirectory() as temp_dir:
        filename = f"{temp_dir}/pipeline.yaml"
        Compiler().compile(
            pipeline_func=test_module.test_pipeline,
            package_path=filename,
        )
        yield filename


def test_uploader(mocker, compiled_pipeline: str):
    """
    Verify single package upload.
    """
    uploader = PipelineUploader()
    client_mock = mocker.patch.object(uploader, "_client")
    uploader.upload(
        compiled_pipeline, "pipeline 0.1.0", "pipeline", "0.1.0", "Description"
    )
    client_mock.upload_pipeline_version.assert_called_once_with(
        compiled_pipeline,
        "pipeline 0.1.0",
        "0.1.0",
        pipeline_name="pipeline",
        description="Description",
    )


async def test_updater(mocker, compiled_pipeline: str, temp_dir: str):
    """
    Verify entire update cycle.
    """
    config_loader = PipelineConfigLoader()
    mocker.patch.object(
        config_loader,
        "get_config",
        return_value={"default": PipelineSourceConfig("url")},
    )
    updater = PipelineUpdater(temp_dir, config_loader)
    mock_download = mocker.patch.object(
        updater._downloader,
        "get_pipeline_files",
        return_value=(
            True,
            PipelineFileResponse([Path(compiled_pipeline)], "etag", "last-modified"),
        ),
    )
    mock_upload = mocker.patch.object(updater._uploader, "upload")
    await updater.run()
    mock_download.assert_called_once_with("default", "url")
    mock_upload.assert_called_once_with(compiled_pipeline, "default 1.0.0", None)


async def test_updater_skip(mocker, temp_dir):
    """
    Verify that only updated packages are being resubmitted.
    """
    config_loader = PipelineConfigLoader()
    mocker.patch.object(
        config_loader,
        "get_config",
        return_value={"default": PipelineSourceConfig("url")},
    )
    updater = PipelineUpdater(temp_dir, config_loader)
    updater._response_cache = {
        "default": PipelineFileResponse([], "etag", "last-modified")
    }
    mock_download = mocker.patch.object(
        updater._downloader,
        "get_pipeline_files",
        return_value=(
            False,
            None,
        ),
    )
    mock_upload = mocker.patch.object(updater._uploader, "upload")
    await updater.run()
    mock_download.assert_called_once_with(
        "default", "url", etag="etag", last_modified="last-modified"
    )
    mock_upload.assert_not_called()


TEST_URL = "https://example.com/myfile.py"


@pytest.fixture
async def mock_response():
    """
    Provides a mock_response to be filled in tests.
    """
    with aioresponses() as m:
        yield m


@pytest.fixture(scope="session")
async def client():
    """
    Provides a configured pipeline downloader.
    """
    with (
        tempfile.TemporaryDirectory() as temp_dir,
        PipelineDownloader(
            PipelineDownloadConfig(
                local_path=temp_dir,
                max_size=1024,
                chunk_size=256,
            ),
        ) as observer,
    ):
        yield observer


async def test_get_file(mock_response, client):
    """
    Verifies single file retrieval.
    """
    mock_response.get(
        TEST_URL,
        status=200,
        body="test-content",
        headers={"ETag": "etag", "Last-Modified": "last-modified"},
    )
    content = await client.get_pipeline_files("default", TEST_URL)
    filename = client._local_path / "default" / "pipeline.yaml"
    assert content == (
        True,
        PipelineFileResponse([filename], "etag", "last-modified"),
    )


async def test_get_zip_file(mock_response, client):
    """
    Verifies zipped file retrieval.

    NOTE: Currently cannot be done it tests, possible due to limitaitons of mock.
    """
    buffer = BytesIO()
    with NamedTemporaryFile("wt") as temp_file, ZipFile(buffer, "w") as zf:
        temp_file.write("test-content")
        zf.write(temp_file.name)
    mock_response.get(
        TEST_URL,
        status=200,
        body=buffer.getvalue(),
        headers={"ETag": "etag", "Last-Modified": "last-modified"},
    )
    content = await client.get_pipeline_files("default", TEST_URL)
    filename = client._local_path / "default" / "pipeline.yaml"
    assert content == (
        True,
        PipelineFileResponse([filename], "etag", "last-modified"),
    )


@pytest.mark.parametrize(
    "update_args_headers",
    [
        (("etag", None), {"If-None-Match": "etag"}),
        ((None, "last-modified"), {"If-Modified-Since": "last-modified"}),
        (
            ("etag", "last-modified"),
            {"If-None-Match": "etag", "If-Modified-Since": "last-modified"},
        ),
    ],
)
async def test_get_file_not_updated(update_args_headers, mock_response, client):
    """
    Verifies response handling in case file has not been updated remotely.
    """
    update_args, expected_headers = update_args_headers
    mock_response.get(TEST_URL, status=304)
    content = await client.get_pipeline_files("default", TEST_URL, *update_args)
    mock_response.assert_called_once_with(
        TEST_URL, method="GET", headers=expected_headers
    )
    assert content == (False, None)


async def test_size_error_header(mock_response, client):
    """
    Verifies rejecting files that exceed size limit (header check).
    """
    mock_response.get(
        TEST_URL,
        status=200,
        body="test-content",
        headers={
            "Content-Length": "1025",
        },
    )
    with pytest.raises(SizeExceededException):
        await client.get_pipeline_files("default", TEST_URL)


async def test_size_error_content(mock_response, client):
    """
    Verifies rejecting files that exceed size limit (check during download).
    """
    mock_response.get(
        TEST_URL,
        status=200,
        body="test-content-that-is-too-long" * 256,
        headers={
            "Content-Length": "256",
        },
    )
    with pytest.raises(SizeExceededException):
        await client.get_pipeline_files("default", TEST_URL)


async def test_http_status_error(mock_response, client):
    """
    Verifies other HTTP errors are reported.
    """
    mock_response.get(TEST_URL, status=404)
    with pytest.raises(ClientResponseError):
        await client.get_pipeline_files("default", TEST_URL)


async def test_http_unexpected_error(mock_response, client):
    """
    Verifies unknown HTTP error codes that are not error codes are reported.
    """
    mock_response.get(TEST_URL, status=300)
    with pytest.raises(UnexpectedResponseException):
        await client.get_pipeline_files("default", TEST_URL)

from io import BytesIO
from zipfile import ZipFile

from aiohttp import ClientResponseError
from aioresponses import aioresponses

from ml_operator.pipelines.downloader import (
    PipelineDownloader,
    PipelineDownloadConfig,
    PipelineFileResponse,
    SizeExceededException,
    UnexpectedResponseException,
)
import tempfile
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
from kubernetes_asyncio.client import V1ConfigMap

from ml_operator.pipelines.config import PipelineConfigLoader, PipelineSourceConfig
from ml_operator.pipelines.updater import PipelineUpdater


async def test_config(mocker):
    """
    Reading the pipeline configuration from the cluster.
    """
    mock_core_api = mocker.patch(
        "ml_operator.pipelines.config.CoreV1Api.read_namespaced_config_map",
        mocker.AsyncMock(
            return_value=V1ConfigMap(data={"default": '{"url": "<test-url>"}'})
        ),
    )
    config_loader = PipelineConfigLoader()
    assert config_loader.config == {}
    await config_loader.update_config()
    mock_core_api.assert_called_once_with("pipelines", "ml-operator")
    assert config_loader.config == {"default": PipelineSourceConfig("<test-url>", None)}


async def test_updater(mocker, compiled_pipeline: str):
    """
    Verify entire update cycle.
    """
    mock_downloader = mocker.Mock()
    mock_downloader.get_pipeline_files = mocker.AsyncMock(
        return_value=(
            True,
            PipelineFileResponse([Path(compiled_pipeline)], "etag", "last-modified"),
        ),
    )
    updater = PipelineUpdater()
    mock_service = mocker.patch.object(updater._pipeline_service, "upload")
    await updater.run({"default": PipelineSourceConfig("url")}, mock_downloader)
    mock_downloader.get_pipeline_files.assert_called_once_with("default", "url")
    mock_service.assert_called_once_with(
        compiled_pipeline, "test-pipeline 1.0.0", "test-pipeline"
    )


async def test_updater_skip(mocker):
    """
    Verify that only updated packages are being resubmitted.
    """
    mock_downloader = mocker.Mock()
    mock_downloader.get_pipeline_files = mocker.AsyncMock(
        return_value=(
            False,
            None,
        ),
    )
    updater = PipelineUpdater()
    updater._response_cache = {
        "default": PipelineFileResponse([], "etag", "last-modified")
    }
    mock_service = mocker.patch.object(updater._pipeline_service, "upload")
    await updater.run({"default": PipelineSourceConfig("url")}, mock_downloader)
    mock_downloader.get_pipeline_files.assert_called_once_with(
        "default", "url", etag="etag", last_modified="last-modified"
    )
    mock_service.assert_not_called()


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
    with tempfile.TemporaryDirectory() as temp_dir:
        async with PipelineDownloader(
            PipelineDownloadConfig(
                local_path=temp_dir,
                max_size=1024,
                chunk_size=256,
            ),
        ) as observer:
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
    """
    buffer = BytesIO()
    with (
        NamedTemporaryFile("wt", suffix=".yaml") as temp_file,
        ZipFile(buffer, "w") as zf,
    ):
        temp_file.write("test-content")
        zf.write(temp_file.name, arcname="pipeline.yaml")
    mock_response.get(
        TEST_URL,
        status=200,
        body=buffer.getvalue(),
        headers={
            "ETag": "etag",
            "Last-Modified": "last-modified",
            "Content-Type": "zip",
        },
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

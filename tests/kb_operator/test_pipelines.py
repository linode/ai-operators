from io import BytesIO
from zipfile import ZipFile

from aiohttp import ClientResponseError
from aioresponses import aioresponses

import tempfile
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
from kubernetes_asyncio.client import V1ConfigMap, V1Secret, ApiException

from ai_operators.kb_operator.pipelines.config import (
    PipelineConfigLoader,
    PipelineSourceConfig,
    PipelineSourceAuth,
)
from ai_operators.kb_operator.pipelines.downloader import (
    PipelineFileResponse,
    PipelineDownloader,
    PipelineDownloadConfig,
    SizeExceededException,
    UnexpectedResponseException,
)
from ai_operators.kb_operator.pipelines.updater import PipelineUpdater


async def test_config(mocker):
    """
    Reading the pipeline configuration from the cluster.
    """
    mock_config_map = mocker.patch(
        "ai_operators.kb_operator.pipelines.config.CoreV1Api.read_namespaced_config_map",
        mocker.AsyncMock(
            return_value=V1ConfigMap(
                data={
                    "default": '{"url": "<test-url>", "authType": "bearer", "authSecretName": "test-secret", "authSecretKey": "test-key"}'  # pragma: allowlist secret
                }
            )
        ),
    )
    mock_secret = mocker.patch(
        "ai_operators.kb_operator.pipelines.config.CoreV1Api.read_namespaced_secret",
        mocker.AsyncMock(
            return_value=V1Secret(data={"test-key": "dGVzdC12YWx1ZQ=="})  # "test-value"
        ),
    )
    config_loader = PipelineConfigLoader()
    assert config_loader.config == {}
    await config_loader.update_config()
    assert config_loader.config == {
        "default": PipelineSourceConfig(
            "<test-url>", auth_type=PipelineSourceAuth.BEARER, auth_token="test-value"
        )
    }
    mock_config_map.assert_called_once_with("pipelines", "ml-operator")
    mock_secret.assert_called_once_with("test-secret", "ml-operator")


@pytest.mark.parametrize(
    "config_map_value, secret_value",
    [
        pytest.param("invalid-config", None, id="invalid-config"),
        pytest.param(
            '{"url": "<test-url>", "authType": "bearer"}', None, id="no-secret"
        ),
        pytest.param(
            '{"url": "<test-url>", "authType": "bearer", "authSecretName": "test-secret", "authSecretKey": "test-key"}',  # pragma: allowlist secret
            None,
            id="missing-secret",
        ),
        pytest.param(
            '{"url": "<test-url>", "authType": "bearer", "authSecretName": "test-secret", "authSecretKey": "test-key"}',  # pragma: allowlist secret
            {"other-key": "dGVzdC12YWx1ZQ=="},
            id="missing-secret-key",
        ),
        pytest.param(
            '{"url": "<test-url>", "authType": "bearer", "authSecretName": "test-secret", "authSecretKey": "test-key"}',  # pragma: allowlist secret
            {"test-key": "invalid-value"},
            id="invalid-secret-value",
        ),
    ],
)
async def test_config_invalid(config_map_value, secret_value, mocker):
    """
    Valid config entries should be read, invalid existing ones should not be discarded until removed.
    """
    config_loader = PipelineConfigLoader()
    # Initialize with a previously-read valid config
    config_loader._current_config = {
        "default": PipelineSourceConfig(
            "<test-url>", auth_type=PipelineSourceAuth.BEARER, auth_token="test-value"
        ),
        "second": PipelineSourceConfig(
            "<test-url>", auth_type=PipelineSourceAuth.BEARER, auth_token="test-value"
        ),
    }
    mock_config_map = mocker.patch(
        "ai_operators.kb_operator.pipelines.config.CoreV1Api.read_namespaced_config_map",
        mocker.AsyncMock(return_value=V1ConfigMap(data={"default": config_map_value})),
    )
    if secret_value:
        mock_secret_return = mocker.AsyncMock(
            return_value=V1Secret(data={"test-key": "dGVzdC12YWx1ZQ=="})
        )
    else:
        mock_secret_return = mocker.AsyncMock(
            side_effect=ApiException(status=404, reason="Not found.")
        )

    mock_secret = mocker.patch(
        "ai_operators.kb_operator.pipelines.config.CoreV1Api.read_namespaced_secret",
        mock_secret_return,
    )
    await config_loader.update_config()
    config_loader._current_config = {
        "default": PipelineSourceConfig(
            "<test-url>", auth_type=PipelineSourceAuth.BEARER, auth_token="test-value"
        ),
    }
    mock_config_map.assert_called_once_with("pipelines", "ml-operator")
    if secret_value:
        mock_secret.assert_called_once_with("test-secret", "ml-operator")


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
    config = PipelineSourceConfig("url")
    await updater.run({"default": PipelineSourceConfig("url")}, mock_downloader)
    mock_downloader.get_pipeline_files.assert_called_once_with("default", config)
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
    config = PipelineSourceConfig("url")
    await updater.run({"default": config}, mock_downloader)
    mock_downloader.get_pipeline_files.assert_called_once_with(
        "default", config, etag="etag", last_modified="last-modified"
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
    content = await client.get_pipeline_files("default", PipelineSourceConfig(TEST_URL))
    filename = client._local_path / "default" / "pipeline.yaml"
    assert content == (
        True,
        PipelineFileResponse([filename], "etag", "last-modified"),
    )


@pytest.mark.parametrize(
    "source_config_header",
    [
        (
            PipelineSourceConfig(
                TEST_URL, auth_type=PipelineSourceAuth.BASIC, auth_token="test"
            ),
            "Basic dGVzdA==",
        ),
        (
            PipelineSourceConfig(
                TEST_URL, auth_type=PipelineSourceAuth.BEARER, auth_token="test"
            ),
            "Bearer test",
        ),
    ],
)
async def test_get_file_with_auth(source_config_header, mock_response, client):
    """
    Verifies single file retrieval using authentication.
    """
    mock_response.get(
        TEST_URL,
        status=200,
        body="test-content",
        headers={"ETag": "etag", "Last-Modified": "last-modified"},
    )
    source_config, expected_header = source_config_header
    content = await client.get_pipeline_files("default", source_config)
    filename = client._local_path / "default" / "pipeline.yaml"
    assert content == (
        True,
        PipelineFileResponse([filename], "etag", "last-modified"),
    )
    mock_response.assert_called_once_with(
        TEST_URL,
        method="GET",
        headers={
            "Authorization": expected_header,
        },
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
    content = await client.get_pipeline_files("default", PipelineSourceConfig(TEST_URL))
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
    content = await client.get_pipeline_files(
        "default", PipelineSourceConfig(TEST_URL), *update_args
    )
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
        await client.get_pipeline_files("default", PipelineSourceConfig(TEST_URL))


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
        await client.get_pipeline_files("default", PipelineSourceConfig(TEST_URL))


async def test_http_status_error(mock_response, client):
    """
    Verifies other HTTP errors are reported.
    """
    mock_response.get(TEST_URL, status=404)
    with pytest.raises(ClientResponseError):
        await client.get_pipeline_files("default", PipelineSourceConfig(TEST_URL))


async def test_http_unexpected_error(mock_response, client):
    """
    Verifies unknown HTTP error codes that are not error codes are reported.
    """
    mock_response.get(TEST_URL, status=300)
    with pytest.raises(UnexpectedResponseException):
        await client.get_pipeline_files("default", PipelineSourceConfig(TEST_URL))

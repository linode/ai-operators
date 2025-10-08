from unittest.mock import Mock, patch

import pytest
from kfp_server_api import V2beta1PipelineVersion

from ai_operators.ml_operator import KubeflowPipelinesService
from ai_operators.ml_operator import AkamaiKnowledgeBase


@pytest.fixture
def test_kb() -> AkamaiKnowledgeBase:
    return AkamaiKnowledgeBase(
        pipeline_name="test-pipeline",
        pipeline_parameters={
            "url": "https://example.com/data",
            "embedding_model_endpoint": "http://embedding-service",
            "embedding_model_name": "test-model",
            "embedding_dimension": 384,
            "db_host_read_write": "postgres-rw",
            "db_name": "testdb",
            "db_port": 5432,
            "db_secret_name": "postgres-secret",  # pragma: allowlist secret
            "secret_namespace": "test-namespace",  # pragma: allowlist secret
            "table_name": "test-kb",
        },
    )


@pytest.fixture
def service_with_mock_client():
    with patch(
        "ml_operator.services.kubeflow_pipelines_service.Client"
    ) as mock_client_class:
        mock_client = Mock()

        mock_client.upload_pipeline_version.return_value = V2beta1PipelineVersion(
            "pipeline-123", "pipeline-123-456"
        )

        # Pipeline data
        mock_client.get_pipeline_id.return_value = "pipeline-123"

        # Version data
        mock_version = Mock()
        mock_version.pipeline_version_id = "ver-456"
        mock_versions_response = Mock()
        mock_versions_response.pipeline_versions = [mock_version]
        mock_client.list_pipeline_versions.return_value = mock_versions_response

        # Experiment data
        mock_experiment = Mock()
        mock_experiment.experiment_id = "exp-789"
        mock_client.create_experiment.return_value = mock_experiment

        # Run data
        mock_run_result = Mock()
        mock_run_result.run_id = "run-abc"
        mock_client.run_pipeline.return_value = mock_run_result

        # Completion data
        mock_run = Mock()
        mock_run.run_id = "run-abc"
        mock_run.run_details = {"status": "Succeeded"}
        mock_run.created_at = "2024-01-01T12:00:00Z"
        mock_run.finished_at = "2024-01-01T12:30:00Z"
        mock_client.wait_for_run_completion.return_value = mock_run

        mock_client_class.return_value = mock_client
        service = KubeflowPipelinesService("http://test-endpoint")
        yield service, mock_client


@patch("os.getenv")
def test_endpoint_from_parameter(mock_getenv):
    service = KubeflowPipelinesService("http://test-endpoint")
    assert service._kubeflow_endpoint == "http://test-endpoint"
    mock_getenv.assert_not_called()


@patch("os.getenv")
def test_endpoint_from_environment(mock_getenv):
    mock_getenv.return_value = "http://env-endpoint"
    service = KubeflowPipelinesService()

    assert service._kubeflow_endpoint == "http://env-endpoint"
    mock_getenv.assert_called_once_with("KUBEFLOW_ENDPOINT")


def test_missing_endpoint_error():
    service = KubeflowPipelinesService()
    service._kubeflow_endpoint = None

    with pytest.raises(ValueError, match="Kubeflow endpoint not configured"):
        service._get_client()


def test_upload(service_with_mock_client, compiled_pipeline: str):
    """
    Verify single package upload.
    """
    service, mock_client = service_with_mock_client
    result = service.upload(
        compiled_pipeline, "pipeline 0.1.0", "pipeline", "Description"
    )
    assert result == ("pipeline-123", "pipeline-123-456")
    mock_client.upload_pipeline_version.assert_called_once_with(
        compiled_pipeline,
        "pipeline 0.1.0",
        pipeline_id="pipeline-123",
        description="Description",
    )


def test_experiment_creation(service_with_mock_client):
    service, mock_client = service_with_mock_client
    mock_client.create_experiment.return_value.experiment_id = "exp-123"

    result = service._get_or_create_experiment("test-kb")

    assert result == "exp-123"
    mock_client.create_experiment.assert_called_once_with(
        name="test-kb", description="ML-Operator experiment for knowledge base test-kb"
    )


def test_latest_version_retrieval(service_with_mock_client):
    service, mock_client = service_with_mock_client

    result = service._get_latest_pipeline_version("pipeline-123", "test-pipeline")

    assert result == "ver-456"
    mock_client.list_pipeline_versions.assert_called_once_with(
        pipeline_id="pipeline-123", page_size=1, sort_by="created_at desc"
    )


def test_no_versions_found_error(service_with_mock_client):
    service, mock_client = service_with_mock_client
    mock_versions_response = Mock()
    mock_versions_response.pipeline_versions = []
    mock_client.list_pipeline_versions.return_value = mock_versions_response

    with pytest.raises(
        ValueError, match="No versions found for pipeline 'test-pipeline'"
    ):
        service._get_latest_pipeline_version("pipeline-123", "test-pipeline")


def verify_pipeline_execution_calls(mock_client):
    mock_client.get_pipeline_id.assert_called_once_with("test-pipeline")
    mock_client.create_experiment.assert_called_once()

    expected_params = {
        "url": "https://example.com/data",
        "embedding_model_endpoint": "http://embedding-service",
        "embedding_model_name": "test-model",
        "embedding_dimension": 384,
        "db_host_read_write": "postgres-rw",
        "db_name": "testdb",
        "db_port": 5432,
        "db_secret_name": "postgres-secret",  # pragma: allowlist secret
        "table_name": "test-kb",
        "secret_namespace": "test-namespace",  # pragma: allowlist secret
    }

    mock_client.run_pipeline.assert_called_once_with(
        experiment_id="exp-789",
        job_name="test-kb-test-namespace-20240101-120000",
        pipeline_id="pipeline-123",
        version_id="ver-456",
        params=expected_params,
    )


@patch("ml_operator.services.kubeflow_pipelines_service.datetime")
def test_successful_pipeline_run(mock_datetime, test_kb, service_with_mock_client):
    mock_datetime.now.return_value.strftime.return_value = "20240101-120000"
    service, mock_client = service_with_mock_client

    result = service.run_pipeline("test-namespace", "test-kb", test_kb)

    assert result == "run-abc"
    verify_pipeline_execution_calls(mock_client)


def test_missing_pipeline_name(test_kb, service_with_mock_client):
    service, mock_client = service_with_mock_client
    test_kb.pipeline_name = ""

    with pytest.raises(ValueError, match="No pipeline specified"):
        service.run_pipeline("test-namespace", "test-kb", test_kb)


def test_pipeline_not_found(test_kb, service_with_mock_client):
    service, mock_client = service_with_mock_client
    mock_client.get_pipeline_id.return_value = None

    with pytest.raises(ValueError, match="Pipeline 'test-pipeline' not found"):
        service.run_pipeline("test-namespace", "test-kb", test_kb)


def test_successful_completion(service_with_mock_client):
    service, mock_client = service_with_mock_client

    result = service.wait_for_pipeline_completion("run-abc")

    expected_result = {
        "id": "run-abc",
        "details": {"status": "Succeeded"},
        "created_at": "2024-01-01T12:00:00Z",
        "finished_at": "2024-01-01T12:30:00Z",
    }

    assert result == expected_result
    mock_client.wait_for_run_completion.assert_called_once_with("run-abc", 7200)


def test_custom_timeout(service_with_mock_client):
    service, mock_client = service_with_mock_client

    service.wait_for_pipeline_completion("run-abc", timeout=3600)

    mock_client.wait_for_run_completion.assert_called_once_with("run-abc", 3600)


@patch("ml_operator.services.kubeflow_pipelines_service.Client")
def test_client_connection_failure(mock_client_class):
    mock_client_class.side_effect = Exception("Connection refused")
    service = KubeflowPipelinesService("http://invalid-endpoint")

    with pytest.raises(Exception, match="Connection refused"):
        service._get_client()


def test_experiment_creation_error(service_with_mock_client):
    service, mock_client = service_with_mock_client
    mock_client.create_experiment.side_effect = Exception("KFP Error")

    with pytest.raises(Exception, match="KFP Error"):
        service._get_or_create_experiment("test-kb")


def test_version_lookup_error(service_with_mock_client):
    service, mock_client = service_with_mock_client
    mock_client.list_pipeline_versions.side_effect = Exception("Network error")

    with pytest.raises(Exception, match="Network error"):
        service._get_latest_pipeline_version("pipeline-123", "test-pipeline")


def test_pipeline_execution_error(test_kb, service_with_mock_client):
    service, mock_client = service_with_mock_client
    mock_client.run_pipeline.side_effect = Exception("Execution failed")

    with pytest.raises(Exception, match="Execution failed"):
        service.run_pipeline("test-namespace", "test-kb", test_kb)


def test_completion_timeout_error(service_with_mock_client):
    service, mock_client = service_with_mock_client
    mock_client.wait_for_run_completion.side_effect = Exception("Timeout")

    with pytest.raises(Exception, match="Timeout"):
        service.wait_for_pipeline_completion("run-abc")

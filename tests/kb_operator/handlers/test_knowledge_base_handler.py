from unittest.mock import Mock, patch

import pytest

from ai_operators.kb_operator.handlers import KnowledgeBaseHandler
from ai_operators.kb_operator.services import KubeflowPipelinesService
from tests.kb_operator.conftest import SAMPLE_KB_OBJECT


def test_constructor_custom_pipeline_service():
    mock_service = Mock(spec=KubeflowPipelinesService)

    handler = KnowledgeBaseHandler(pipeline_service=mock_service)

    assert handler.pipeline_service is mock_service


@pytest.fixture
def handler_with_mock_service():
    with patch(
        "ai_operators.kb_operator.handlers.knowledge_base_handler.KubeflowPipelinesService"
    ) as mock_service_class:
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        handler = KnowledgeBaseHandler()
        yield handler, mock_service


async def test_start_pipeline_success(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.run_pipeline.return_value = "test-run-id"

    result = await handler._start_pipeline(
        "test-namespace", "test-kb", SAMPLE_KB_OBJECT, "created"
    )

    assert result == "test-run-id"
    mock_service.run_pipeline.assert_called_once_with(
        "test-namespace", "test-kb", SAMPLE_KB_OBJECT
    )


async def test_start_pipeline_service_failure(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.run_pipeline.side_effect = Exception("Pipeline service failed")

    with pytest.raises(Exception, match="Pipeline service failed"):
        await handler._start_pipeline(
            "test-namespace", "test-kb", SAMPLE_KB_OBJECT, "created"
        )


async def test_created_success(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.run_pipeline.return_value = "created-run-id"

    result = await handler.created("test-namespace", "test-kb", SAMPLE_KB_OBJECT)

    assert result == "created-run-id"
    mock_service.run_pipeline.assert_called_once_with(
        "test-namespace", "test-kb", SAMPLE_KB_OBJECT
    )


async def test_created_pipeline_failure(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.run_pipeline.side_effect = Exception("Creation pipeline failed")

    with pytest.raises(Exception, match="Creation pipeline failed"):
        await handler.created("test-namespace", "test-kb", SAMPLE_KB_OBJECT)


async def test_updated_success(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.run_pipeline.return_value = "updated-run-id"

    result = await handler.updated("test-namespace", "test-kb", SAMPLE_KB_OBJECT)

    assert result == "updated-run-id"
    mock_service.run_pipeline.assert_called_once_with(
        "test-namespace", "test-kb", SAMPLE_KB_OBJECT
    )


async def test_updated_pipeline_failure(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.run_pipeline.side_effect = Exception("Update pipeline failed")

    with pytest.raises(Exception, match="Update pipeline failed"):
        await handler.updated("test-namespace", "test-kb", SAMPLE_KB_OBJECT)


async def test_deleted(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service

    result = await handler.deleted("test-namespace", "test-kb", SAMPLE_KB_OBJECT)

    assert result is None
    mock_service.run_pipeline.assert_not_called()
    mock_service.wait_for_pipeline_completion.assert_not_called()


async def test_wait_for_completion_success(handler_with_mock_service):
    expected_result = {
        "id": "test-run-id",
        "details": {"status": "Succeeded"},
        "created_at": "2024-01-01T12:00:00Z",
        "finished_at": "2024-01-01T12:30:00Z",
    }
    handler, mock_service = handler_with_mock_service
    mock_service.wait_for_pipeline_completion.return_value = expected_result

    result = await handler.wait_for_completion(
        "test-namespace", "test-kb", "test-run-id"
    )

    assert result == expected_result
    mock_service.wait_for_pipeline_completion.assert_called_once_with("test-run-id")


async def test_wait_for_completion_failure(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.wait_for_pipeline_completion.side_effect = Exception(
        "Completion wait failed"
    )

    with pytest.raises(Exception, match="Completion wait failed"):
        await handler.wait_for_completion("test-namespace", "test-kb", "test-run-id")


async def test_wait_for_completion_timeout(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.wait_for_pipeline_completion.side_effect = TimeoutError(
        "Pipeline execution timed out"
    )

    with pytest.raises(TimeoutError, match="Pipeline execution timed out"):
        await handler.wait_for_completion("test-namespace", "test-kb", "test-run-id")


def test_constructor_logger_initialization():
    handler = KnowledgeBaseHandler()

    assert handler.logger is not None
    assert (
        handler.logger.name
        == "ai_operators.kb_operator.handlers.knowledge_base_handler"
    )


async def test_created_and_updated_use_different_actions(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.run_pipeline.return_value = "test-run-id"

    result1 = await handler.created("test-namespace", "test-kb", SAMPLE_KB_OBJECT)
    result2 = await handler.updated("test-namespace", "test-kb", SAMPLE_KB_OBJECT)

    assert result1 == "test-run-id"
    assert result2 == "test-run-id"
    assert mock_service.run_pipeline.call_count == 2


async def test_start_pipeline_parameters_validation(handler_with_mock_service):
    handler, mock_service = handler_with_mock_service
    mock_service.run_pipeline.return_value = "validation-run-id"

    namespace = "validation-namespace"
    name = "validation-kb"
    kb_object = SAMPLE_KB_OBJECT

    result = await handler._start_pipeline(namespace, name, kb_object, "validation")

    mock_service.run_pipeline.assert_called_once_with(namespace, name, kb_object)
    assert result == "validation-run-id"

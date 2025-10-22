import logging
from typing import Optional

from ..services import KubeflowPipelinesService
from ..resource import AkamaiKnowledgeBase
from ..utils.status import (
    get_kb_indexing_status,
    get_kb_indexed_status,
    get_kb_failed_status,
)


class KnowledgeBaseHandler:
    def __init__(self, pipeline_service: Optional[KubeflowPipelinesService] = None):
        self.pipeline_service = pipeline_service or KubeflowPipelinesService()
        self.logger = logging.getLogger(__name__)

    async def _start_pipeline(
        self, namespace: str, name: str, kb: AkamaiKnowledgeBase, action: str
    ) -> str:
        try:
            run_id = self.pipeline_service.run_pipeline(namespace, name, kb)
            self.logger.info(
                f"Started {action} embedding pipeline for {name} in {namespace}. Run ID: {run_id}"
            )
            return run_id
        except Exception as e:
            self.logger.error(
                f"Failed to start {action} embedding pipeline for {name} in {namespace}: {e}"
            )
            raise

    async def created(
        self, namespace: str, name: str, kb: AkamaiKnowledgeBase
    ) -> tuple[str, dict]:
        """
        Start indexing pipeline for created knowledge base.

        Returns:
            Tuple of (run_id, status_dict)
        """
        self.logger.info(
            f"Processing created knowledge base {name} in namespace {namespace}"
        )
        run_id = await self._start_pipeline(namespace, name, kb, "")
        return run_id, get_kb_indexing_status(name, run_id).to_dict()

    async def updated(
        self, namespace: str, name: str, kb: AkamaiKnowledgeBase
    ) -> tuple[str, dict]:
        """
        Start indexing pipeline for updated knowledge base.

        Returns:
            Tuple of (run_id, status_dict)
        """
        self.logger.info(
            f"Processing updated knowledge base {name} in namespace {namespace}"
        )
        run_id = await self._start_pipeline(namespace, name, kb, "updated")
        return run_id, get_kb_indexing_status(name, run_id).to_dict()

    async def deleted(self, namespace: str, name: str, kb: AkamaiKnowledgeBase):
        self.logger.info(f"Knowledge base {name} in namespace {namespace} deleted")

        # Future: Add cleanup logic here
        # - Stop running a pipeline if it is running
        # - Archive pipeline and experiments in kubeflow pipelines
        # - Delete table from a pgvector database?
        pass

    # TODO check if this does not exhaust memory and connection pool on high load and long waits
    async def wait_for_completion(self, namespace: str, name: str, run_id: str) -> dict:
        """
        Wait for pipeline to complete and return appropriate status.

        Returns:
            Status dict (Indexed or Failed)
        """
        try:
            result = self.pipeline_service.wait_for_pipeline_completion(run_id)
            self.logger.info(
                f"Pipeline completed for {name} in {namespace}. Final status: {result}"
            )
            return get_kb_indexed_status(name).to_dict()
        except Exception as e:
            self.logger.error(f"Pipeline failed for {name} in {namespace}: {e}")
            raise

    def mark_failed(self, reason: str, error_message: str) -> dict:
        """
        Create a failed status for a knowledge base.

        Called by Kopf error handlers after all retries are exhausted.
        """
        self.logger.error(f"Knowledge base failed: {reason} - {error_message}")
        return get_kb_failed_status(reason, error_message).to_dict()

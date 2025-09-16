import os
from datetime import datetime
from typing import Optional

from kfp.client import Client

from ..constants import EMBED_BATCH_SIZE
from ..resource import AkamaiKnowledgeBase


class KubeflowPipelinesService:
    def __init__(self, kubeflow_endpoint: Optional[str] = None):
        self.kubeflow_endpoint = kubeflow_endpoint or os.getenv("KUBEFLOW_ENDPOINT")
        self.client: Optional[Client] = None

    def _get_client(self) -> Client:
        if not self.client:
            if not self.kubeflow_endpoint:
                raise ValueError("Kubeflow endpoint not configured. Set KUBEFLOW_ENDPOINT environment variable.")
            self.client = Client(host=self.kubeflow_endpoint)
        return self.client

    def run_pipeline(self, namespace: str, name: str, kb: AkamaiKnowledgeBase) -> str:
        client = self._get_client()

        pipeline_name = kb.indexing.embedding_pipeline
        if not pipeline_name:
            raise ValueError(f"No embedding pipeline specified for knowledge base {name}")

        # Get pipeline ID from pipeline name
        pipeline_id = client.get_pipeline_id(pipeline_name)
        if not pipeline_id:
            raise ValueError(f"Pipeline '{pipeline_name}' not found in Kubeflow")

        parameters = {
            "url": kb.data.url,
            "table_name": name,
            "embedding_model": kb.indexing.embedding_model_name,
            "embedding_api_base": kb.indexing.embedding_model_endpoint,
            "embed_dim": kb.indexing.embedding_dimension,
            "embed_batch_size": EMBED_BATCH_SIZE,
            "secret_name": kb.indexing.db_secret_name,
            "secret_namespace": namespace,
        }

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_result = client.run_pipeline(
            job_name=f"{name}-{namespace}-{timestamp}",
            pipeline_id=pipeline_id,
            params=parameters
        )

        return run_result.run_id

    def wait_for_pipeline_completion(self, run_id: str, timeout: int = 7200) -> dict:
        client = self._get_client()
        run = client.wait_for_run_completion(run_id, timeout)
        return {
            "id": run.run_id,
            "details": run.run_details,
            "created_at": run.created_at,
            "finished_at": run.finished_at
        }

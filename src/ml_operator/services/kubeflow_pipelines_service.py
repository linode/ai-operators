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
                raise ValueError(
                    "Kubeflow endpoint not configured. Set KUBEFLOW_ENDPOINT environment variable."
                )
            self.client = Client(host=self.kubeflow_endpoint)
        return self.client

    def _get_or_create_experiment(self, name: str) -> str:
        client = self._get_client()
        """This function checks if an experiment exists, and creates it if not."""
        experiment = client.create_experiment(
            name=name, description=f"ML-Operator experiment for knowledge base {name}"
        )
        return experiment.experiment_id

    def _get_latest_pipeline_version(self, pipeline_id, pipeline_name):
        client = self._get_client()
        """Same fetch is used in kfp UI (page_size=1&sort_by=created_at%20desc)"""
        versions = client.list_pipeline_versions(
            pipeline_id=pipeline_id, page_size=1, sort_by="created_at desc"
        )
        if not versions.pipeline_versions:
            raise ValueError(f"No versions found for pipeline '{pipeline_name}'")
        version_id = versions.pipeline_versions[0].pipeline_version_id
        return version_id

    def run_pipeline(self, namespace: str, name: str, kb: AkamaiKnowledgeBase) -> str:
        client = self._get_client()

        pipeline_name = kb.indexing.embedding_pipeline
        if not pipeline_name:
            raise ValueError(
                f"No embedding pipeline specified for knowledge base {name}"
            )

        pipeline_id = client.get_pipeline_id(pipeline_name)
        if not pipeline_id:
            raise ValueError(f"Pipeline '{pipeline_name}' not found in Kubeflow")

        version_id = self._get_latest_pipeline_version(pipeline_id, pipeline_name)

        experiment_id = self._get_or_create_experiment(name)

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
            experiment_id=experiment_id,
            job_name=f"{name}-{namespace}-{timestamp}",
            pipeline_id=pipeline_id,
            version_id=version_id,
            params=parameters,
        )

        return run_result.run_id

    def wait_for_pipeline_completion(self, run_id: str, timeout: int = 7200) -> dict:
        client = self._get_client()
        run = client.wait_for_run_completion(run_id, timeout)
        return {
            "id": run.run_id,
            "details": run.run_details,
            "created_at": run.created_at,
            "finished_at": run.finished_at,
        }

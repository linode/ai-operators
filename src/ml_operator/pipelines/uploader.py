from kfp import Client
from kfp.dsl.base_component import BaseComponent
from kfp_server_api import V2beta1PipelineVersion


class PipelineUploader:
    """
    Uploads a Kubeflow pipeline from a loaded component.
    """

    def __init__(self):
        self._client = None

    def _get_client(self) -> Client:
        if self._client:
            return self._client
        self._client = client = Client()
        return client

    def upload(
        self,
        pipeline_func: BaseComponent,
        name: str,
        version: str = "1.0.0",
        description: str | None = None,
    ) -> V2beta1PipelineVersion:
        return self._get_client().upload_pipeline_version_from_pipeline_func(
            pipeline_func,
            version,
            pipeline_name=name,
            description=description,
        )

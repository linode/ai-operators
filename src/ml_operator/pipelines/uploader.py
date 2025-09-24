import logging

from kfp import Client
from kfp_server_api import V2beta1PipelineVersion
from kubernetes_asyncio.client import ApiException

logger = logging.getLogger(__name__)


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
        package_path: str,
        version_name: str,
        pipeline_name: str = None,
        version: str = "1.0.0",
        description: str | None = None,
    ) -> V2beta1PipelineVersion:
        """
        Performs the upload of a single pipeline package.
        """
        try:
            return self._get_client().upload_pipeline_version(
                package_path,
                version_name,
                version,
                pipeline_name=pipeline_name,
                description=description,
            )
        except ApiException as e:
            logger.error(f"Error uploading pipeline '{version_name}'", exc_info=e)

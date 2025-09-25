import logging
from pathlib import Path

from .config import PipelineSourceConfig
from .downloader import PipelineDownloader, PipelineFileResponse
from ..services import KubeflowPipelinesService

logger = logging.getLogger(__name__)


class PipelineUpdater:
    """
    Performs the entire cycle of updating all configured files to uploading pipelines.
    """

    def __init__(self):
        self._pipeline_service = KubeflowPipelinesService()
        self._response_cache: dict[str, PipelineFileResponse] = {}

    def _upload_pipeline(
        self, package_path: Path, version_name: str, pipeline_name
    ) -> tuple[str, str | None]:
        return self._pipeline_service.upload(
            str(package_path), version_name, pipeline_name
        )

    async def update_source(
        self, downloader: PipelineDownloader, name: str, config: PipelineSourceConfig
    ):
        """
        Updates a single configured link, and uploads all (new) pipelines found.
        """
        kwargs = {}
        if last_response := self._response_cache.get(name):
            kwargs["etag"] = last_response.etag
            kwargs["last_modified"] = last_response.last_modified
        logger.debug(f"Checking on pipeline source updates for '{name}'")
        is_updated, response = await downloader.get_pipeline_files(
            name, config.url, **kwargs
        )  # type: bool, PipelineFileResponse
        if is_updated:
            version = config.version or "1.0.0"
            logger.debug(f"Processing files: {response.file_paths}")
            for file_path in response.file_paths:
                pipeline_name = file_path.name.removesuffix(".yaml")
                self._upload_pipeline(
                    file_path,
                    f"{pipeline_name} {version}",
                    pipeline_name,
                )
            self._response_cache[name] = response

    async def run(
        self, config: dict[str, PipelineSourceConfig], downloader: PipelineDownloader
    ):
        """
        Triggers an update cycle over all configured urls.
        """
        for source_name, source_config in config.items():
            try:
                await self.update_source(downloader, source_name, source_config)
            except Exception as e:
                logger.error(
                    f"Error updating pipeline source '{source_name}'", exc_info=e
                )

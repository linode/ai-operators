import logging

from .config import PipelineSourceConfig
from .downloader import PipelineDownloader, PipelineFileResponse
from .uploader import PipelineUploader

logger = logging.getLogger(__name__)


class PipelineUpdater:
    """
    Performs the entire cycle of updating all configured files to uploading pipelines.
    """

    def __init__(self):
        self._uploader = PipelineUploader()
        self._response_cache: dict[str, PipelineFileResponse] = {}

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
            has_multiple = len(response.file_paths) > 1
            version = config.version or "1.0.0"
            logger.debug(f"Processing files: {response.file_paths}")
            if has_multiple:
                for file_path in response.file_paths:
                    self._uploader.upload(
                        str(file_path),
                        f"{name}-{file_path.name.removesuffix('.yaml')} {version}",
                        version,
                    )
            else:
                self._uploader.upload(
                    str(response.file_paths[0]), f"{name} {version}", config.version
                )
            self._response_cache = response

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

import logging
from pathlib import Path

from .config import PipelineConfigLoader, PipelineSourceConfig
from .downloader import PipelineDownloader, PipelineDownloadConfig, PipelineFileResponse
from .uploader import PipelineUploader


class PipelineUpdater:
    """
    Performs the entire cycle of updating all configured files to uploading pipelines.
    """

    def __init__(self, local_root: str | Path, config_loader: PipelineConfigLoader):
        self._local_root = local_root
        self._downloader = PipelineDownloader(PipelineDownloadConfig(local_root))
        self._uploader = PipelineUploader()
        self._config_loader = config_loader
        self._response_cache: dict[str, PipelineFileResponse] = {}

    async def update_repo(self, name: str, config: PipelineSourceConfig):
        """
        Updates a single configured link, and uploads all (new) pipelines found.
        """
        kwargs = {}
        if last_response := self._response_cache.get(name):
            kwargs["etag"] = last_response.etag
            kwargs["last_modified"] = last_response.last_modified
        is_updated, response = await self._downloader.get_pipeline_files(
            name, config.url, **kwargs
        )  # type: bool, PipelineFileResponse
        if is_updated:
            has_multiple = len(response.file_paths) > 1
            version = config.version or "1.0.0"
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

    async def run(self):
        """
        Triggers an update cycle over all configured urls.
        """
        config = self._config_loader.get_config()
        for repo_name, repo_config in config.items():
            try:
                await self.update_repo(repo_name, repo_config)
            except Exception as e:
                logging.error(e)

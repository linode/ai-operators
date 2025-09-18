import logging
from pathlib import Path

from .config import PipelineConfigLoader, PipelineRepoConfig
from .extractor import get_pipeline_items
from .repo_manager import RepoManager
from .uploader import PipelineUploader


class PipelineUpdater:
    """
    Performs the entire cycle of updating all configured repositories to uploading pipelines.
    """

    def __init__(self, repo_root: str | Path, config_loader: PipelineConfigLoader):
        self._repo_root = Path(repo_root)
        self._uploader = PipelineUploader()
        self._config_loader = config_loader

    def update_repo(self, name: str, config: PipelineRepoConfig):
        """
        Updates a single configured repository, and uploads all (new) pipelines found.
        """
        repo_path = self._repo_root / name
        repo_manager = RepoManager(config.url, repo_path, config.ref)
        updated_paths = repo_manager.update_repo()
        pipeline_versions = get_pipeline_items(updated_paths)
        for pipeline_version in pipeline_versions:
            try:
                self._uploader.upload(
                    pipeline_version.func,
                    pipeline_version.func.name,
                    pipeline_version.version,
                )
            except Exception as e:
                logging.error(e)

    async def run(self):
        """
        Triggers an update cycle over all configured repositories.
        """
        config = self._config_loader.get_config()
        for repo_name, repo_config in config.items():
            try:
                self.update_repo(repo_name, repo_config)
            except Exception as e:
                logging.error(e)

import logging
from pathlib import Path
from shutil import rmtree

from git import Repo, GitError, Commit, Tree, Blob

logger = logging.getLogger(__name__)


def _get_files_diff(
    root_path: Path, old_commit: Commit, new_commit: Commit
) -> list[Path]:
    diff = new_commit.diff(old_commit)
    return [root_path / diff_item.a_path for diff_item in diff]


def _get_files(root_path: Path, tree: Tree) -> list[Path]:
    all_entries = []
    for entry in tree:
        if entry.type == Tree.type:
            all_entries.extend(_get_files(root_path, entry))
        elif entry.type == Blob.type:
            all_entries.append(root_path / entry.path)
    return all_entries


class RepoInvalidRef(Exception):
    """
    Reference is not found in repository.
    """

    pass


class RepoManager:
    """
    Manages a copy of a remote repository, detecting incremental updates.
    """

    def __init__(self, repo_url: str, repo_local: str | Path, ref: str = "main"):
        self._repo_url = repo_url
        self._repo_local = Path(repo_local)
        self._repo: Repo | None = None
        self._target_ref = ref or "main"

    def init_repo(self) -> list[Path]:
        """
        Initializes the local repository copy.

        If the local directory exists, it is removed.
        """
        logger.info(f"Initializing repository at {self._repo_local}.")
        self._repo = None
        if not self._repo_local.parent.exists():
            logger.info("Creating parent directory.")
            self._repo_local.parent.mkdir(parents=True)
        if self._repo_local.exists():
            logger.info("Cleaning up old copy.")
            rmtree(self._repo_local)
        logger.info("Cloning.")
        self._repo = repo = Repo.clone_from(self._repo_url, self._repo_local)
        if self._target_ref not in self._repo.refs:
            raise RepoInvalidRef(self._target_ref)
        head = self._repo.create_head(self._target_ref)
        head.checkout()
        return _get_files(Path(repo.working_dir), repo.head.commit.tree)

    def update_repo(self) -> list[Path]:
        """
        Performs an incremental update of the repository and returns
        paths to all updated files.

        If that fails, or the repository has not been initialized,
        starts with a fresh clone of the remote repository.
        """
        if not self._repo_local.exists():
            return self.init_repo()
        else:
            self._repo = Repo(self._repo_local)
        if self._repo.is_dirty():
            logger.info("Resetting repository.")
            self._repo.head.reset(f"origin/{self._target_ref}", working_tree=True)
        origin = self._repo.remotes.origin
        logger.debug("Fetching changes.")
        fetch_info = origin.fetch()[0]
        if self._repo.head.ref == fetch_info.ref:
            logger.debug("No changes detected.")
            return []
        else:
            old_commit = self._repo.head.commit
            try:
                logger.info("Pulling changes.")
                origin.pull(no_rebase=True)
            except GitError as e:
                logger.warning("Caught exception, trying to re-initialize.")
                logger.error(e)
                return self.init_repo()
            else:
                new_commit = self._repo.head.commit
                return _get_files_diff(
                    Path(self._repo.working_dir), old_commit, new_commit
                )

import os
import tempfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

import pytest
from kfp.dsl.base_component import BaseComponent
from kubernetes_asyncio.client import V1ConfigMap

from ml_operator.pipelines.config import PipelineConfigLoader, PipelineRepoConfig
from ml_operator.pipelines.repo_manager import Repo, RepoManager, RepoInvalidRef
from ml_operator.pipelines import extractor
from ml_operator.pipelines.updater import PipelineUpdater
from ml_operator.pipelines.uploader import PipelineUploader


async def test_config(mocker):
    mock_core_api = mocker.patch(
        "ml_operator.pipelines.config.CoreV1Api.read_namespaced_config_map",
        return_value=V1ConfigMap(
            data={"repositories": {"default": {"url": "<test-url>"}}}
        ),
    )
    config_loader = PipelineConfigLoader()
    assert config_loader.get_config() == {}
    await config_loader.update_config()
    mock_core_api.assert_called_once_with("pipelines", "ml-operator")
    assert config_loader.get_config() == {
        "default": PipelineRepoConfig("<test-url>", None)
    }


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as path:
        yield path


def add_repo_files(
    repo: Repo, paths_contents: Iterable[tuple[str, str]], commit_msg: str | None = None
):
    index_paths: list[str] = []
    root_path = Path(repo.working_dir)
    for path, content in paths_contents:
        file_path = Path(root_path / path)
        parent_dir = file_path.parent
        if not parent_dir.exists():
            parent_dir.mkdir(parents=True)
        with (root_path / path).open("w") as f:
            f.write(content)
        index_paths.append(path)
    repo.index.add(index_paths)
    if commit_msg:
        repo.index.commit(commit_msg)


@pytest.fixture
def remote_repo(mocker, temp_dir):
    repo = Repo.init(temp_dir, initial_branch="main")
    add_repo_files(repo, [("README.md", "# Test")], "Initial commit.")

    _original_clone_from = Repo.clone_from

    def clone_new(_remote_url, *args, **kwargs):
        return _original_clone_from(temp_dir, *args, **kwargs)

    mocker.patch.object(Repo, "clone_from", new=clone_new)
    yield repo


@pytest.mark.parametrize("update", [True, False])
def test_repo_init(remote_repo: Repo, temp_dir: str, update: bool):
    repo_dir = Path(temp_dir) / "repo"
    manager = RepoManager("url", repo_dir)
    if update:
        result = manager.update_repo()
    else:
        result = manager.init_repo()
    assert repo_dir.is_dir()
    assert (repo_dir / "README.md").is_file()
    assert result == [
        repo_dir / "README.md",
    ]


def test_repo_invalid_ref(remote_repo: Repo, temp_dir: str):
    repo_dir = Path(temp_dir) / "repo"
    manager = RepoManager("url", repo_dir, "nonexistent")
    with pytest.raises(RepoInvalidRef):
        manager.init_repo()


def test_repo_update(remote_repo: Repo, temp_dir: str):
    repo_dir = Path(temp_dir) / "repo"
    manager = RepoManager("url", repo_dir)
    manager.init_repo()
    add_repo_files(
        remote_repo,
        [
            ("subDir/subDir2/test.py", "print('Test')"),
            ("subDir/test.py", "print('Test')"),
            ("test.txt", "Some text"),
        ],
        commit_msg="Added files.",
    )

    result = manager.update_repo()
    assert result == [
        repo_dir / "subDir" / "subDir2" / "test.py",
        repo_dir / "subDir" / "test.py",
        repo_dir / "test.txt",
    ]


@pytest.mark.parametrize("local_commit", [False, True])
def test_repo_update_dirty(
    mocker, remote_repo: Repo, temp_dir: str, local_commit: bool
):
    repo_dir = Path(temp_dir) / "repo"
    manager = RepoManager("url", repo_dir)
    manager.init_repo()

    add_repo_files(
        remote_repo,
        [
            ("subDir/test.py", "print('Test')"),
            ("test.txt", "Some text"),
        ],
        commit_msg="Added remote files.",
    )
    add_repo_files(
        manager._repo,
        [
            ("subDir/test2.py", "print('Test')"),
            ("test.txt", "Some text, too"),
        ],
        commit_msg="Added local files." if local_commit else None,
    )
    init_spy = mocker.spy(manager, "init_repo")

    result = manager.update_repo()
    if local_commit:
        init_spy.assert_called_once()
        assert result == [
            repo_dir / "README.md",
            repo_dir / "subDir" / "test.py",
            repo_dir / "test.txt",
        ]
    else:
        init_spy.assert_not_called()
        assert result == [
            repo_dir / "subDir" / "test.py",
            repo_dir / "test.txt",
        ]


PIPELINE_SCRIPT = """\
from kfp import dsl

PIPELINE_FUNC_NAME = "test_pipeline"
PIPELINE_VERSION = "0.1.0"

@dsl.component(
    base_image='nvcr.io/nvidia/ai-workbench/python-cuda117:1.0.3',
    packages_to_install=['psycopg2-binary', 'llama-index', 'llama-index-vector-stores-postgres',
                         'llama-index-embeddings-openai-like', 'kubernetes']
)
def cmp():
    return "Hello!"

@dsl.pipeline(name='test-pipeline')
def test_pipeline():
    cmp()
"""


@pytest.fixture(scope="session")
def pipeline_script():
    with NamedTemporaryFile("wt", suffix=".py", delete=False) as f:
        f.write(PIPELINE_SCRIPT)
    yield Path(f.name)
    try:
        os.unlink(f.name)
    except Exception:
        pass


def test_extractor_load(pipeline_script: Path):
    result = extractor.load_module(pipeline_script)
    assert isinstance(result.test_pipeline, BaseComponent)
    assert isinstance(result.cmp, BaseComponent)
    assert result.PIPELINE_FUNC_NAME == "test_pipeline"


def test_extractor_pipelines(pipeline_script: Path):
    result = list(extractor.get_pipeline_items([pipeline_script]))
    assert len(result) == 1
    assert isinstance(result[0], extractor.PipelineVersion)
    assert isinstance(result[0].func, BaseComponent)
    assert result[0].version == "0.1.0"


def test_uploader(mocker):
    uploader = PipelineUploader()
    client_mock = mocker.patch.object(uploader, "_client")

    def dummy_func():
        pass

    uploader.upload(dummy_func, "pipeline", "0.1.0", "Description")
    client_mock.upload_pipeline_version_from_pipeline_func.assert_called_once_with(
        dummy_func, "0.1.0", pipeline_name="pipeline", description="Description"
    )


async def test_updater(mocker, remote_repo: Repo, temp_dir: str):
    repo_dir = Path(temp_dir) / "default"
    manager = RepoManager("url", repo_dir)
    manager.init_repo()
    add_repo_files(
        remote_repo,
        [
            ("test_pipeline.py", PIPELINE_SCRIPT),
        ],
        commit_msg="Added files.",
    )
    config_loader = PipelineConfigLoader()
    mocker.patch.object(
        config_loader, "get_config", return_value={"default": PipelineRepoConfig("url")}
    )
    updater = PipelineUpdater(temp_dir, config_loader)
    mock_upload = mocker.patch.object(updater._uploader, "upload")
    await updater.run()
    mock_upload.assert_called_once()
    assert isinstance(mock_upload.call_args.args[0], BaseComponent)
    assert mock_upload.call_args.args[1:] == ("test-pipeline", "0.1.0")

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
from kfp.compiler import Compiler

from ml_operator.resource import AkamaiKnowledgeBase

# Global test objects, reused in tests
SAMPLE_KB_DICT = {
    "pipelineName": "custom-pipeline",
    "pipelineParameters": {
        "url": "https://example.com/kb-data",
        "embeddingModelEndpoint": "model.model-namespace.svc.cluster.local",
        "embeddingModelName": "e5-mistral-7b",
        "embeddingDimension": 4096,
        "dbHostReadWrite": "pgvector-rw.team-demo.svc.cluster.local",
        "dbHostRead": "pgvector-r.team-demo.svc.cluster.local",
        "dbName": "app",
        "dbPort": 5432,
        "dbSecretName": "pgvector-app",
    },
}

SAMPLE_KB_OBJECT = AkamaiKnowledgeBase(
    pipeline_name="custom-pipeline",
    pipeline_parameters={
        "url": "https://example.com/kb-data",
        "embeddingModelEndpoint": "model.model-namespace.svc.cluster.local",
        "embeddingModelName": "e5-mistral-7b",
        "embeddingDimension": 4096,
        "dbHostReadWrite": "pgvector-rw.team-demo.svc.cluster.local",
        "dbHostRead": "pgvector-r.team-demo.svc.cluster.local",
        "dbName": "app",
        "dbPort": 5432,
        "dbSecretName": "pgvector-app",
    },
)


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
    """
    Provides a raw pipeline script for tests.
    """
    with tempfile.NamedTemporaryFile("wt", suffix=".py", delete=False) as f:
        f.write(PIPELINE_SCRIPT)
    yield Path(f.name)
    try:
        os.unlink(f.name)
    except Exception:
        pass


@pytest.fixture(scope="session")
def compiled_pipeline(pipeline_script: Path):
    """
    Provides a compiled pipeline package.
    """
    mod_path = str(pipeline_script.parent)
    mod_name = pipeline_script.name.removesuffix(".py")
    sys.path.insert(0, mod_path)
    try:
        test_module = importlib.import_module(mod_name)
    finally:
        sys.path.remove(mod_path)
    with tempfile.TemporaryDirectory() as temp_dir:
        filename = f"{temp_dir}/pipeline.yaml"
        Compiler().compile(
            pipeline_func=test_module.test_pipeline,
            package_path=filename,
        )
        yield filename


@pytest.fixture
def temp_dir():
    """
    Provides a temporary directory per function.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as path:
        yield path

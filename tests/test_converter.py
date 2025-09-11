from pathlib import Path

import yaml

from src.ml_operator.converter import converter
from src.ml_operator.resource import AkamaiKnowledgeBase, KBData, KBIndexing

# Global test objects, reused in tests
with open(Path(__file__).parent / "sample-spec.yaml", "r") as f:
    SAMPLE_KB_DICT = yaml.safe_load(f)

SAMPLE_KB_OBJECT = AkamaiKnowledgeBase(
    data=KBData(url="https://example.com/kb-data"),
    indexing=KBIndexing(
        embedding_model_endpoint="model.model-namespace.svc.cluster.local",
        embedding_model_name="e5-mistral-7b",
        embedding_dimension=4096,
        embedding_pipeline="pipeline",
        db_host_read_write="pgvector-rw.team-demo.svc.cluster.local",
        db_host_read="pgvector-r.team-demo.svc.cluster.local",
        db_name="app",
        db_port=5432,
        db_secret_name="pgvector-app",
    ),
)


def test_deserialization():
    """
    Verifies that the deserialized structure matches the Python object representation
    """
    obj = converter.structure(SAMPLE_KB_DICT, AkamaiKnowledgeBase)
    assert SAMPLE_KB_OBJECT == obj


def test_serialization():
    """
    Verifies that the serialized Python dict matches the sample stored in the YAML file.
    """
    serialized = converter.unstructure(SAMPLE_KB_OBJECT)
    assert SAMPLE_KB_DICT == serialized

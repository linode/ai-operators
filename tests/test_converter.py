from ml_operator.converter import converter
from ml_operator.resource import AkamaiKnowledgeBase
from .common import SAMPLE_KB_OBJECT, SAMPLE_KB_DICT


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

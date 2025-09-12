from typing import Any

from attrs import define

from .converter import converter


@define
class KBData:
    url: str


@define
class KBIndexing:
    embedding_model_endpoint: str
    embedding_model_name: str
    embedding_dimension: int
    embedding_pipeline: str
    db_host_read_write: str
    db_host_read: str
    db_name: str
    db_port: int
    db_secret_name: str


@define
class AkamaiKnowledgeBase:
    data: KBData
    indexing: KBIndexing

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "AkamaiKnowledgeBase":
        return converter.structure(spec, cls)

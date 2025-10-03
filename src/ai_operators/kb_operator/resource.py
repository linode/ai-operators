from typing import Any

from attrs import define

from ai_operators.ml_operator.converter import converter


@define
class AkamaiKnowledgeBase:
    pipeline_name: str
    pipeline_parameters: dict[str, Any]

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "AkamaiKnowledgeBase":
        return converter.structure(spec, cls)

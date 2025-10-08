from typing import Any, List, Dict

from attrs import define, field

from ai_operators.agent_operator.converter import converter


@define
class AkamaiAgent:
    foundation_model: str
    agent_instructions: str
    max_tokens: int = 512
    # TODO make this strongly typed
    routes: List[Dict[str, Any]] = field(factory=list)
    tools: List[Dict[str, Any]] = field(factory=list)

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "AkamaiAgent":
        return converter.structure(spec, cls)


@define
class AkamaiKnowledgeBase:
    pipeline_name: str
    pipeline_parameters: dict[str, Any]

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "AkamaiKnowledgeBase":
        return converter.structure(spec, cls)

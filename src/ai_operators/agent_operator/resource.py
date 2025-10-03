from typing import Any, List, Dict

from attrs import define, field

from ai_operators.agent_operator.converter import converter


@define
class AkamaiAgent:
    foundation_model: str
    system_prompt: str
    routes: List[Dict[str, Any]] = field(factory=list)
    tools: List[Dict[str, Any]] = field(factory=list)

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "AkamaiAgent":
        return converter.structure(spec, cls)

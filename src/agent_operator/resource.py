from typing import Any, Optional

from attrs import define

from converter import converter

@define
class AkamaiAgent:
    foundation_model: str
    system_prompt: str
    knowledge_base: Optional[str] = None

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "AkamaiAgent":
        return converter.structure(spec, cls)

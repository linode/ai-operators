from typing import Any
from attrs import define

from ai_operators.agent_operator.utils.k8s import fetch_knowledge_base_config


@define
class KBData:
    """Data class for knowledge base configuration."""

    name: str
    pipeline_name: str
    pipeline_parameters: dict[str, Any]

    def to_config_dict(self) -> dict[str, Any]:
        """Convert to config dict format expected by agent tools."""
        return {
            "pipeline_name": self.pipeline_name,
            **self.pipeline_parameters,
        }


async def create_kb_data(namespace: str, kb_name: str) -> "KBData":
    kb_cr = await fetch_knowledge_base_config(namespace, kb_name)

    return KBData(
        name=kb_name,
        pipeline_name=kb_cr.pipeline_name,
        pipeline_parameters=kb_cr.pipeline_parameters,
    )

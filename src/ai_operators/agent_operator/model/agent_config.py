from typing import Dict, Any, List
from attrs import define

from ai_operators.agent_operator.model.agent_data import AgentData


@define
class FoundationModelConfig:
    """Configuration for foundation model."""

    name: str
    endpoint: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "endpoint": self.endpoint,
        }


@define
class AgentConfig:
    """Agent configuration to be stored in ConfigMap."""

    namespace: str
    name: str
    foundation_model: FoundationModelConfig
    agent_instructions: str
    max_tokens: int
    routes: List[Dict[str, Any]]
    tools: List[Dict[str, Any]]

    @classmethod
    def from_agent_data(cls, agent_data: AgentData) -> "AgentConfig":
        """Create AgentConfig from AgentData."""
        # Sanitize tool names to snake_case for LlamaIndex
        sanitized_tools = []
        for tool in agent_data.tools:
            tool_copy = tool.copy()
            if "name" in tool_copy:
                tool_copy["name"] = tool_copy["name"].replace("-", "_")
            sanitized_tools.append(tool_copy)

        return cls(
            namespace=agent_data.namespace,
            name=agent_data.name,
            foundation_model=FoundationModelConfig(
                name=agent_data.foundation_model,
                endpoint=agent_data.foundation_model_endpoint,
            ),
            agent_instructions=agent_data.agent_instructions,
            max_tokens=agent_data.max_tokens,
            routes=agent_data.routes,
            tools=sanitized_tools,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict format for ConfigMap."""
        return {
            "namespace": self.namespace,
            "name": self.name,
            "foundation_model": self.foundation_model.to_dict(),
            "agent_instructions": self.agent_instructions,
            "max_tokens": self.max_tokens,
            "routes": self.routes,
            "tools": self.tools,
        }

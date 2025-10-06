from typing import Dict, Any, List
from attrs import define, field

from ai_operators.agent_operator.resource import AkamaiAgent
from ai_operators.agent_operator.utils.k8s import get_foundation_model_endpoint
from ai_operators.agent_operator.model.kb_data import create_kb_data


@define
class AgentData:
    """Data class for agent deployment configuration."""

    namespace: str
    name: str
    foundation_model: str
    foundation_model_endpoint: str
    system_prompt: str
    # TODO make this strongly typed
    routes: List[Dict[str, Any]] = field(factory=list)
    tools: List[Dict[str, Any]] = field(factory=list)


async def create_agent_data(namespace: str, name: str, agent: AkamaiAgent) -> AgentData:
    """Create AgentData from AkamaiAgent resource."""

    tools = []
    for tool in agent.tools:
        tool_copy = tool.copy()

        # Sanitize tool name to snake_case
        if "name" in tool_copy:
            tool_copy["name"] = tool_copy["name"].replace("-", "_")

        if tool.get("type") == "knowledgeBase":
            kb_name = tool_copy.get("name")
            if kb_name:
                kb_data = await create_kb_data(namespace, kb_name)
                tool_copy["config"] = kb_data.to_config_dict()

        tools.append(tool_copy)

    # Get foundation model endpoint from service discovery
    foundation_model_endpoint = await get_foundation_model_endpoint(
        agent.foundation_model
    )

    return AgentData(
        namespace=namespace,
        name=name,
        foundation_model=agent.foundation_model,
        foundation_model_endpoint=foundation_model_endpoint,
        system_prompt=agent.system_prompt,
        routes=agent.routes.copy(),
        tools=tools,
    )

from typing import Dict, Any, List
from attrs import define, field

from agent_operator.resource import AkamaiAgent
from .k8s import fetch_knowledge_base_config, get_foundation_model_endpoint


@define
class AgentData:
    """Data class for agent deployment configuration."""

    namespace: str
    name: str
    foundation_model: str
    foundation_model_endpoint: str
    system_prompt: str
    """TODO make this strongly typed"""
    routes: List[Dict[str, Any]] = field(factory=list)
    tools: List[Dict[str, Any]] = field(factory=list)


async def create_agent_data(namespace: str, name: str, agent: AkamaiAgent) -> AgentData:
    """Create AgentData from AkamaiAgent resource."""

    # Enrich tools - fetch KB configs for knowledgeBase tools
    enriched_tools = []
    for tool in agent.tools:
        tool_copy = tool.copy()

        if tool.get("type") == "knowledgeBase":
            # Fetch KB CR and merge its config
            kb_name = tool.get("name")
            if kb_name:
                kb_config = await fetch_knowledge_base_config(namespace, kb_name)
                tool_copy["config"] = kb_config

        enriched_tools.append(tool_copy)

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
        tools=enriched_tools,
    )

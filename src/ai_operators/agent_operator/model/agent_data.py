from typing import Dict, Any, List
from attrs import define, field

from ai_operators.agent_operator.resource import AkamaiAgent
from ai_operators.agent_operator.model.kb_data import create_kb_data


@define
class AgentData:
    """Data class for agent deployment configuration."""

    namespace: str
    name: str
    foundation_model: str
    foundation_model_endpoint: str
    agent_instructions: str
    max_tokens: int
    temperature: float = 0.7
    top_p: float = 1.0
    # TODO make this strongly typed
    routes: List[Dict[str, Any]] = field(factory=list)
    tools: List[Dict[str, Any]] = field(factory=list)

    @staticmethod
    def for_deletion(namespace: str, name: str, agent: AkamaiAgent) -> "AgentData":
        return AgentData(
            namespace=namespace,
            name=name,
            foundation_model=agent.foundation_model,
            foundation_model_endpoint="",  # Not needed for deletion
            agent_instructions=agent.agent_instructions,
            max_tokens=agent.max_tokens,
            temperature=agent.temperature,
            top_p=agent.top_p,
            routes=[],
            tools=[],
        )

    @staticmethod
    def for_status_check(namespace: str, name: str) -> "AgentData":
        return AgentData(
            namespace=namespace,
            name=name,
            foundation_model="",
            foundation_model_endpoint="",
            agent_instructions="",
            max_tokens=0,
            temperature=0.0,
            top_p=0.0,
            routes=[],
            tools=[],
        )


async def create_agent_data(namespace: str, name: str, agent: AkamaiAgent) -> AgentData:
    tools = []
    for tool in agent.tools:
        tool_copy = tool.copy()

        if tool.get("type") == "knowledgeBase":
            kb_name = tool.get("name")
            if kb_name:
                kb_data = await create_kb_data(namespace, kb_name)
                tool_copy["config"] = kb_data.to_config_dict()

        tools.append(tool_copy)

    return AgentData(
        namespace=namespace,
        name=name,
        foundation_model=agent.foundation_model,
        foundation_model_endpoint=agent.foundation_model_endpoint,
        agent_instructions=agent.agent_instructions,
        max_tokens=agent.max_tokens,
        temperature=agent.temperature,
        top_p=agent.top_p,
        routes=agent.routes.copy(),
        tools=tools,
    )

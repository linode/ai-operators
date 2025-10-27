"""
WARNING: Changes to this file should be reflected in the agent/templates/pipeline-configmap.yaml

Defines the Pipeline class for managing a complex AI agent with various tools integration.

This module establishes an AI agent pipeline for handling tasks such as working with
knowledge bases, function tools, and external MCP servers, configured dynamically
through JSON. It supports embedding integration and vector-based indexing,
using a range of third-party libraries.
"""

import json
import anyio
import base64
from functools import partial
from typing import Dict, Any
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec
from llama_index.core.tools import QueryEngineTool, FunctionTool
from llama_index.core.agent.workflow import AgentWorkflow, AgentStream
from llama_index.core.workflow import Context
from llama_index.core import Settings, VectorStoreIndex
from llama_index.llms.openai_like import OpenAILike
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from llama_index.vector_stores.postgres import PGVectorStore

from kubernetes import client, config as k8s_config


class Pipeline:
    def __init__(self):
        self.name = None
        self.agent_config = None
        self.index = None
        self.agent = None
        self.ctx = None

    async def on_startup(self):
        # Load config from mounted ConfigMap
        config_path = "/config/agent-config.json"
        with open(config_path, "r") as f:
            self.agent_config = json.load(f)

        self.name = self.agent_config["name"]

        # Build agent from config
        await self._build_agent_from_config()

    async def _build_agent_from_config(self):
        # Load LLM from config
        llm = OpenAILike(
            model=self.agent_config["foundation_model"]["name"],
            api_base=f"{self.agent_config['foundation_model']['endpoint']}",
            max_tokens=512,
            is_chat_model=True,
            timeout=120.0,
            max_retries=2,
        )

        Settings.llm = llm

        # Set up embedding model globally (assumes all KBs use the same embedding model)
        for tool_spec in self.agent_config.get("tools", []):
            if tool_spec.get("type") == "knowledgeBase" and "config" in tool_spec:
                kb_config = tool_spec["config"]

                embedding_model = kb_config.get("embedding_model")
                embedding_api_base = kb_config.get("embedding_api_base")

                if embedding_model and embedding_api_base:
                    Settings.embed_model = OpenAILikeEmbedding(
                        model_name=embedding_model,
                        api_base=embedding_api_base,
                        embed_batch_size=kb_config.get("embed_batch_size", 10),
                        max_retries=3,
                        timeout=180.0,
                    )
                    break  # Only set once from first KB

        # Dynamically build tools from config
        tools = []
        for tool_spec in self.agent_config.get("tools", []):
            tool_type = tool_spec.get("type")

            if tool_type == "knowledgeBase":
                # Build knowledge base tool if config is present
                if "config" in tool_spec:
                    kb_config = tool_spec["config"]
                    kb_name = tool_spec.get("name", "knowledge_base")

                    index = self._build_vector_index(kb_config, kb_name)
                    query_engine = index.as_query_engine(similarity_top_k=3)
                    tool = QueryEngineTool.from_defaults(
                        query_engine=query_engine,
                        name=f"{kb_name}_knowledge_base",
                        description=tool_spec.get(
                            "description", "Knowledge base search tool"
                        ),
                    )
                    tools.append(tool)

            elif tool_type == "function":
                # API-based function tool
                if not tool_spec.get("apiUrl"):
                    print(
                        f"Warning: function tool '{tool_spec.get('name')}' missing apiUrl, skipping"
                    )
                    continue
                fn = partial(self._call_external_api, tool_spec)
                tool = FunctionTool.from_defaults(
                    fn=fn,
                    name=f"{tool_spec.get('name')}_function",
                    description=tool_spec.get("description", "Function tool"),
                )
                tools.append(tool)

            elif tool_type == "subWorkflow":
                # SubWorkflow tool (N8N, Dify, Flowise) - same as API-based function
                if not tool_spec.get("apiUrl"):
                    print(
                        f"Warning: subWorkflow tool '{tool_spec.get('name')}' missing apiUrl, skipping"
                    )
                    continue
                # Use partial to bind tool_spec
                fn = partial(self._call_external_api, tool_spec)
                tool = FunctionTool.from_defaults(
                    fn=fn,
                    name=f"{tool_spec.get('name')}_workflow",
                    description=tool_spec.get(
                        "description", "Workflow automation tool"
                    ),
                )
                tools.append(tool)

            elif tool_type == "mcpServer":
                # MCP server tool - skip if endpoint is unreachable
                try:
                    endpoint = tool_spec.get("apiUrl") or tool_spec.get("endpoint")
                    api_key = tool_spec.get("apiKey")

                    # Create MCP client with auth headers if API key is provided
                    if api_key:
                        mcp_client = BasicMCPClient(
                            endpoint, headers={"Authorization": f"Bearer {api_key}"}
                        )
                    else:
                        mcp_client = BasicMCPClient(endpoint)

                    mcp_tool = McpToolSpec(client=mcp_client)
                    tools.extend(await mcp_tool.to_tool_list_async())
                except Exception as e:
                    endpoint = tool_spec.get("apiUrl") or tool_spec.get("endpoint")
                    print(
                        f"Warning: Failed to connect to MCP server at {endpoint}: {e}"
                    )

        system_prompt = self.agent_config.get(
            "system_prompt", "You are a helpful AI assistant."
        )

        self.agent = AgentWorkflow.from_tools_or_functions(
            tools,
            llm=llm,
            verbose=True,
            system_prompt=system_prompt,
        )
        self.ctx = Context(self.agent)

    def _build_vector_index(self, kb_config: Dict[str, Any], kb_name: str):
        """Builds a vector index based on KB config."""
        db_credentials = self._get_db_credentials(kb_config)

        vector_store = PGVectorStore.from_params(
            database=kb_name,  # Database name is the same as KB name
            host=db_credentials["host"],
            port=db_credentials["port"],
            user=db_credentials["username"],
            password=db_credentials["password"],
            table_name=kb_config.get("table_name"),
            embed_dim=int(kb_config.get("embed_dim")),
        )
        return VectorStoreIndex.from_vector_store(vector_store)

    def _call_external_api(self, tool_spec: Dict[str, Any], query: str) -> str:
        """Call an external API endpoint with authentication.

        This function makes HTTP POST requests to external APIs with Bearer token authentication.
        It's used by function tools and subWorkflow tools to integrate with external services.
        The LLM will format the query parameter based on the tool's description.

        Args:
            tool_spec: Tool specification containing apiUrl, apiKey, and name
            query: The query from the LLM - can be a JSON string or plain text

        Returns:
            The response text from the API, or an error message if the call fails
        """
        import requests

        api_url = tool_spec.get("apiUrl")
        api_key = tool_spec.get("apiKey")
        tool_name = tool_spec.get("name", "api_function")

        # Try to parse query as JSON, otherwise wrap it in a query field
        try:
            body = json.loads(query) if isinstance(query, str) else query
        except (json.JSONDecodeError, TypeError):
            body = {"query": query}

        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            response = requests.post(api_url, json=body, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Error calling {tool_name}: {str(e)}"

    def _get_db_credentials(self, kb_config: Dict[str, Any]):
        """Get database credentials from Kubernetes secret."""
        k8s_config.load_incluster_config()
        v1 = client.CoreV1Api()
        secret = v1.read_namespaced_secret(
            name=kb_config.get("secret_name"),
            namespace=kb_config.get("secret_namespace", self.agent_config["namespace"]),
        )
        return {
            "username": base64.b64decode(secret.data["username"]).decode("utf-8"),
            "password": base64.b64decode(secret.data["password"]).decode("utf-8"),
            "host": base64.b64decode(secret.data["host"]).decode("utf-8"),
            "port": int(base64.b64decode(secret.data["port"]).decode("utf-8")),
        }

    def pipe(self, user_message, model_id, messages, body):
        async def stream_agent():
            handler = self.agent.run(user_message, ctx=self.ctx)
            async for ev in handler.stream_events():
                if isinstance(ev, AgentStream):
                    yield ev.delta
            await handler

        async_gen = stream_agent()
        try:
            while True:
                chunk = anyio.from_thread.run(async_gen.__anext__)
                yield chunk
        except StopAsyncIteration:
            return

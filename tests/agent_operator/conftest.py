from ai_operators.agent_operator.resource import AkamaiAgent

# Global test objects, reused in tests
SAMPLE_AGENT_DICT = {
    "foundationModel": "llama",
    "foundationModelEndpoint": "http://llama-service:8080/openai/v1",
    "agentInstructions": "You're a helpful AI assistant",
    "maxTokens": 512,
    "temperature": 0.7,
    "topP": 0.9,
    "routes": [
        {
            "agent": "specialist-agent",
            "condition": "If the question is about specialized topics",
            "apiUrl": "https://specialist.example.com/v1/chat",
        }
    ],
    "tools": [
        {
            "type": "knowledgeBase",
            "name": "test-kb",
            "description": "Test knowledge base",
        },
        {
            "type": "function",
            "name": "web_search",
            "description": "Search the web",
            "apiUrl": "https://search-api.example.com/search",
        },
        {
            "type": "subWorkflow",
            "name": "email-workflow",
            "description": "Send emails via N8N",
            "apiUrl": "https://n8n.example.com/webhook/send-email",
        },
    ],
}

SAMPLE_AGENT_OBJECT = AkamaiAgent(
    foundation_model="llama",
    foundation_model_endpoint="http://llama-service:8080/openai/v1",
    agent_instructions="You're a helpful AI assistant",
    max_tokens=512,
    temperature=0.7,
    top_p=0.9,
    routes=[
        {
            "agent": "specialist-agent",
            "condition": "If the question is about specialized topics",
            "apiUrl": "https://specialist.example.com/v1/chat",
        }
    ],
    tools=[
        {
            "type": "knowledgeBase",
            "name": "test-kb",
            "description": "Test knowledge base",
        },
        {
            "type": "function",
            "name": "web_search",
            "description": "Search the web",
            "apiUrl": "https://search-api.example.com/search",
        },
    ],
)

# Test objects for updates
UPDATED_AGENT_DICT = {
    "foundationModel": "llama",
    "foundationModelEndpoint": "http://llama-service:8080/openai/v1",
    "agentInstructions": "You're an updated helpful AI assistant",
    "maxTokens": 1024,
    "temperature": 0.7,
    "topP": 0.9,
    "routes": [
        {
            "agent": "updated-specialist",
            "condition": "If the question is about updated topics",
            "apiUrl": "https://updated-specialist.example.com/v1/chat",
        }
    ],
    "tools": [
        {
            "type": "knowledgeBase",
            "name": "test-kb",
            "description": "Updated knowledge base",
        },
        {
            "type": "mcpServer",
            "name": "mcp-tools",
            "description": "MCP server tools",
            "apiUrl": "https://mcp.example.com/api",
        },
    ],
}

UPDATED_AGENT_OBJECT = AkamaiAgent(
    foundation_model="llama",
    foundation_model_endpoint="http://llama-service:8080/openai/v1",
    agent_instructions="You're an updated helpful AI assistant",
    max_tokens=1024,
    temperature=0.7,
    top_p=0.9,
    routes=[
        {
            "agent": "updated-specialist",
            "condition": "If the question is about updated topics",
            "apiUrl": "https://updated-specialist.example.com/v1/chat",
        }
    ],
    tools=[
        {
            "type": "knowledgeBase",
            "name": "test-kb",
            "description": "Updated knowledge base",
        }
    ],
)

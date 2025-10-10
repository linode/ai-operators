from ai_operators.agent_operator.resource import AkamaiAgent

# Global test objects, reused in tests
SAMPLE_AGENT_DICT = {
    "foundationModel": "llama",
    "agentInstructions": "You're a helpful AI assistant",
    "maxTokens": 512,
    "knowledgeBase": "test-kb",
}

SAMPLE_AGENT_OBJECT = AkamaiAgent(
    foundation_model="llama",
    agent_instructions="You're a helpful AI assistant",
    max_tokens=512,
    tools=[],
)

# Test objects for updates
UPDATED_AGENT_DICT = {
    "foundationModel": "llama",
    "agentInstructions": "You're an updated helpful AI assistant",
    "maxTokens": 1024,
    "knowledgeBase": "test-kb",
}

UPDATED_AGENT_OBJECT = AkamaiAgent(
    foundation_model="llama",
    agent_instructions="You're an updated helpful AI assistant",
    max_tokens=1024,
    tools=[],
)

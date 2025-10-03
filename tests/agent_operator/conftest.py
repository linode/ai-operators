from ai_operators.agent_operator import AkamaiAgent

# Global test objects, reused in tests
SAMPLE_AGENT_DICT = {
    "foundationModel": "llama",
    "systemPrompt": "You're a helpful AI assistant",
    "knowledgeBase": "test-kb",
}

SAMPLE_AGENT_OBJECT = AkamaiAgent(
    foundation_model="llama",
    system_prompt="You're a helpful AI assistant",
    knowledge_base="test-kb",
)

# Test objects for updates
UPDATED_AGENT_DICT = {
    "foundationModel": "llama",
    "systemPrompt": "You're an updated helpful AI assistant",
    "knowledgeBase": "test-kb",
}

UPDATED_AGENT_OBJECT = AkamaiAgent(
    foundation_model="llama",
    system_prompt="You're an updated helpful AI assistant",
    knowledge_base="test-kb",
)

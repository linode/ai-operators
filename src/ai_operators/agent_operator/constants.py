import os

CUSTOM_API_ARGS = {
    "group": "akamai.io",
    "version": "v1alpha1",
    "plural": "akamaiagents",
}
RESOURCE_NAME = f"{CUSTOM_API_ARGS['plural']}.{CUSTOM_API_ARGS['group']}"

KB_CUSTOM_API_ARGS = {
    "group": "akamai.io",
    "version": "v1alpha1",
    "plural": "akamaiknowledgebases",
}

PROVIDER = os.getenv("PROVIDER", "apl")
CHART_PATH = os.getenv("CHART_PATH", "/app/agent")

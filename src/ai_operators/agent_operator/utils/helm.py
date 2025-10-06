import json
import logging
import os
import subprocess
import tempfile
import yaml
from typing import Dict, Any

from ai_operators.agent_operator.model.agent_data import AgentData
from ai_operators.agent_operator.model.agent_config import AgentConfig
from ai_operators.agent_operator.constants import CHART_PATH

logger = logging.getLogger(__name__)


def create_helm_values(agent_data: AgentData) -> Dict[str, Any]:
    """Create Helm values for agent chart deployment."""
    agent_config = AgentConfig.from_agent_data(agent_data)

    values = {
        "nameOverride": agent_data.name,
        "agentConfig": json.dumps(agent_config.to_dict(), indent=2),
    }

    return values


def template_agent_chart(
    agent_name: str, namespace: str, values: Dict[str, Any], output_dir: str
) -> str:
    """
    Template the agent Helm chart and save manifests to the output directory.

    """
    chart_path = CHART_PATH
    release_name = f"agent-{agent_name}"

    # Create temporary values file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(values, f)
        values_file = f.name

    try:
        # Create output directory for this agent's manifests
        agent_output_dir = os.path.join("/tmp/agents", agent_name)
        os.makedirs(agent_output_dir, exist_ok=True)

        # Run helm template command with --output-dir
        cmd = [
            "helm",
            "template",
            release_name,
            chart_path,
            "--values",
            values_file,
            "--namespace",
            namespace,
            "--output-dir",
            agent_output_dir,
        ]

        # Set HOME to /tmp for helm to create cache directories
        env = os.environ.copy()
        env["HOME"] = "/tmp"

        subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)

        logger.info(
            f"Successfully templated chart for agent {agent_name} to {agent_output_dir}"
        )
        return agent_output_dir

    except subprocess.CalledProcessError as e:
        logger.error(f"Helm template failed for agent {agent_name}: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error templating chart for agent {agent_name}: {e}")
        raise
    finally:
        # Clean up temporary values file
        os.unlink(values_file)

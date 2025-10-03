import json
import logging
import os
import subprocess
import tempfile
import yaml
from typing import Dict, Any

from .agent_data import AgentData
from ..constants import CHART_PATH

logger = logging.getLogger(__name__)


def _create_agent_config(agent_data: AgentData) -> Dict[str, Any]:
    """Create agent configuration dict to be stored in ConfigMap."""
    return {
        "namespace": agent_data.namespace,
        "name": agent_data.name,
        "foundation_model": {
            "name": agent_data.foundation_model,
            "endpoint": agent_data.foundation_model_endpoint,
        },
        "system_prompt": agent_data.system_prompt,
        "routes": agent_data.routes,
        "tools": agent_data.tools,
    }


def create_helm_values(agent_data: AgentData) -> Dict[str, Any]:
    """Create Helm values for agent chart deployment."""
    # Generate agent config
    agent_config = _create_agent_config(agent_data)

    values = {
        "nameOverride": agent_data.name,
        "agentConfig": json.dumps(agent_config, indent=2),
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
        # Run helm template command
        manifest_file = os.path.join(output_dir, f"{agent_name}.yaml")
        cmd = [
            "helm",
            "template",
            release_name,
            chart_path,
            "--values",
            values_file,
            "--namespace",
            namespace,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Write manifests to file
        with open(manifest_file, "w") as f:
            f.write(result.stdout)

        logger.info(
            f"Successfully templated chart for agent {agent_name} to {manifest_file}"
        )
        return manifest_file

    except subprocess.CalledProcessError as e:
        logger.error(f"Helm template failed for agent {agent_name}: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error templating chart for agent {agent_name}: {e}")
        raise
    finally:
        # Clean up temporary values file
        os.unlink(values_file)

from typing import Dict, Any, List
from datetime import datetime, UTC
from attrs import define, asdict, Factory


@define
class Condition:
    type: str
    status: str
    reason: str
    message: str
    lastTransitionTime: str = Factory(lambda: datetime.now(UTC).isoformat())
    lastUpdateTime: str = Factory(lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@define
class Status:
    phase: str
    conditions: List[Condition]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "conditions": [condition.to_dict() for condition in self.conditions],
        }


def get_agent_deployed_status(name: str) -> Status:
    return Status(
        phase="Deployed",
        conditions=[
            Condition(
                type="AgentDeployed",
                status="True",
                reason="Scheduled",
                message=f"Agent successfully deployed with ID: {name}",
            )
        ],
    )


def get_agent_failed_status(name: str, error: str) -> Status:
    return Status(
        phase="Failed",
        conditions=[
            Condition(
                type="AgentFailed",
                status="True",
                reason="DeploymentError",
                message=f"Agent {name} deployment failed: {error}",
            )
        ],
    )

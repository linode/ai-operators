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
    """
    Status for when deployment resources are created but not yet ready.

    Phase: Deployed - indicates resources exist but pods may not be ready yet.
    """
    return Status(
        phase="Deployed",
        conditions=[
            Condition(
                type="AgentDeployed",
                status="True",
                reason="Scheduled",
                message=f"Agent successfully deployed with ID: {name}",
            ),
            Condition(
                type="AgentReady",
                status="Unknown",
                reason="Pending",
                message="Waiting for pods to become ready",
            ),
        ],
    )


def get_agent_running_status(name: str) -> Status:
    """
    Status for when deployment is ready and serving traffic.

    Phase: Running - indicates pods are ready and passing readiness probes.
    """
    return Status(
        phase="Running",
        conditions=[
            Condition(
                type="AgentDeployed",
                status="True",
                reason="Scheduled",
                message=f"Agent successfully deployed with ID: {name}",
            ),
            Condition(
                type="AgentReady",
                status="True",
                reason="PodsReady",
                message="Agent is ready and serving traffic",
            ),
        ],
    )


def get_agent_failed_status(reason: str, error: str) -> Status:
    return Status(
        phase="Failed",
        conditions=[
            Condition(
                type="AgentFailed",
                status="True",
                reason=reason,
                message=error,
            )
        ],
    )


def get_agent_deployed_not_ready_status(name: str, reason: str) -> Status:
    """
    Status for when deployment succeeded but readiness check failed/timed out.

    Phase: Deployed - resources exist but pods haven't become ready within timeout.
    This is still "Deployed" phase because the deployment exists, just not ready yet.
    """
    return Status(
        phase="Deployed",
        conditions=[
            Condition(
                type="AgentDeployed",
                status="True",
                reason="Scheduled",
                message=f"Agent successfully deployed with ID: {name}",
            ),
            Condition(
                type="AgentReady",
                status="False",
                reason="ReadinessTimeout",
                message=f"Agent deployed but not ready: {reason}",
            ),
        ],
    )

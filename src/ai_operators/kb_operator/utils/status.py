"""Status helper functions for Knowledge Base operator."""

from datetime import datetime, timezone
from typing import Dict, Any
from attrs import define


@define
class Condition:
    """Condition for KB status."""

    type: str
    status: str
    reason: str
    message: str
    lastTransitionTime: str = None
    lastUpdateTime: str = None

    def to_dict(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "type": self.type,
            "status": self.status,
            "reason": self.reason,
            "message": self.message,
            "lastTransitionTime": self.lastTransitionTime or now,
            "lastUpdateTime": self.lastUpdateTime or now,
        }


@define
class Status:
    """Status for KB resource."""

    phase: str
    conditions: list[Condition]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "conditions": [c.to_dict() for c in self.conditions],
        }


def get_kb_indexing_status(name: str, run_id: str) -> Status:
    """
    Status for when indexing pipeline has started.

    Phase: Indexing - pipeline is running.
    """
    return Status(
        phase="Indexing",
        conditions=[
            Condition(
                type="IndexingStarted",
                status="True",
                reason="Scheduled",
                message=f"Indexing pipeline started for knowledge base {name}. Run ID: {run_id}",
            )
        ],
    )


def get_kb_indexed_status(name: str) -> Status:
    """
    Status for when indexing pipeline has completed successfully.

    Phase: Indexed - pipeline completed, knowledge base is ready.
    """
    return Status(
        phase="Indexed",
        conditions=[
            Condition(
                type="IndexingStarted",
                status="True",
                reason="Scheduled",
                message=f"Indexing pipeline started for knowledge base {name}",
            ),
            Condition(
                type="IndexingFinished",
                status="True",
                reason="Completed",
                message="Indexing pipeline completed successfully",
            ),
        ],
    )


def get_kb_failed_status(reason: str, error: str) -> Status:
    """
    Status for when indexing pipeline has failed.

    Phase: Failed - pipeline failed with error.
    """
    return Status(
        phase="Failed",
        conditions=[
            Condition(
                type="IndexingFailed",
                status="True",
                reason=reason,
                message=error,
            )
        ],
    )

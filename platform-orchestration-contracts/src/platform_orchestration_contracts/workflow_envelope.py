"""Workflow input envelope schema.

Standard envelope for every workflow start. Contains references and stable
identifiers — not large payloads. Heavyweight inputs are stored in S3-compatible
object storage; Temporal retains orchestration state and durable references.

See ADR-036 section 3.1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class RequestedBy:
    """Identity of the human or service that initiated the workflow."""

    subject_id: str
    actor_type: str = "user"  # "user" | "service" | "agent"


@dataclass(frozen=True)
class GovernanceBlock:
    """Governance flags that drive workflow control flow."""

    approval_required: bool = False
    approval_policy: Optional[str] = None
    dry_run: bool = False
    force_regenerate: bool = False
    reason: Optional[str] = None


@dataclass(frozen=True)
class InputRef:
    """Reference to the heavyweight input payload stored in object storage."""

    kind: str  # "s3-json-manifest" | "s3-archive" | "inline-json"
    uri: str
    checksum: str  # "sha256:..."


@dataclass(frozen=True)
class WorkflowEnvelope:
    """Standard input envelope for every Temporal workflow start.

    Immutable. Carry this through every activity and child workflow so that
    correlation, causation, and governance state are always available.

    Three distinct version identifiers govern different concerns:
    - ``contract_version``: serialization/schema compatibility (this envelope).
    - ``workflow_type``: business-process behavior (e.g. ``media.corpus-batch.v1``).
    - Package version: client library release (set in pyproject.toml).
    """

    request_id: str
    workflow_id: str
    workflow_type: str  # e.g. "media.corpus-batch.v1"
    source_app: str  # e.g. "casting-signal"
    tenant_id: str
    idempotency_key: str
    requested_by: RequestedBy
    input_ref: InputRef
    contract_version: str = "1.0"
    governance: GovernanceBlock = field(default_factory=GovernanceBlock)
    project_id: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    priority: str = "batch"  # "interactive" | "batch" | "background"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "request_id": self.request_id,
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "source_app": self.source_app,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "idempotency_key": self.idempotency_key,
            "requested_by": {
                "subject_id": self.requested_by.subject_id,
                "actor_type": self.requested_by.actor_type,
            },
            "priority": self.priority,
            "governance": {
                "approval_required": self.governance.approval_required,
                "approval_policy": self.governance.approval_policy,
                "dry_run": self.governance.dry_run,
                "force_regenerate": self.governance.force_regenerate,
                "reason": self.governance.reason,
            },
            "input_ref": {
                "kind": self.input_ref.kind,
                "uri": self.input_ref.uri,
                "checksum": self.input_ref.checksum,
            },
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowEnvelope":
        rb = data["requested_by"]
        gov = data.get("governance", {})
        ref = data["input_ref"]
        return cls(
            contract_version=data.get("contract_version", "1.0"),
            request_id=data["request_id"],
            workflow_id=data["workflow_id"],
            workflow_type=data["workflow_type"],
            source_app=data["source_app"],
            tenant_id=data["tenant_id"],
            idempotency_key=data["idempotency_key"],
            requested_by=RequestedBy(
                subject_id=rb["subject_id"],
                actor_type=rb.get("actor_type", "user"),
            ),
            input_ref=InputRef(
                kind=ref["kind"],
                uri=ref["uri"],
                checksum=ref["checksum"],
            ),
            governance=GovernanceBlock(
                approval_required=gov.get("approval_required", False),
                approval_policy=gov.get("approval_policy"),
                dry_run=gov.get("dry_run", False),
                force_regenerate=gov.get("force_regenerate", False),
                reason=gov.get("reason"),
            ),
            project_id=data.get("project_id"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            priority=data.get("priority", "batch"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )

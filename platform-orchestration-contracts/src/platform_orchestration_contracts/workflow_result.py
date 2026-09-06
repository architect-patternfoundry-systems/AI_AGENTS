"""Workflow result envelope schema.

Standard portable result that every workflow produces on completion.
See ADR-036 section 3.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Canonical workflow status values projected to UIs and downstream consumers.
WORKFLOW_STATUS_VALUES = frozenset(
    {
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
        "awaiting_approval",
        "degraded",
    }
)


@dataclass(frozen=True)
class Summary:
    """Aggregate counts for batch-style workflows."""

    requested_items: int = 0
    generated_items: int = 0
    skipped_items: int = 0
    failed_items: int = 0


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to a durable artifact in object storage."""

    kind: str  # "audio-manifest" | "audio-wav" | "transcript" | "batch-result"
    uri: str  # s3://...
    checksum: str  # "sha256:..."


@dataclass(frozen=True)
class CatalogRef:
    """Reference to a catalog entry in a domain system (e.g. Nexus)."""

    system: str  # "nexus"
    entity_type: str  # "audio-corpus-batch"
    entity_id: str


@dataclass(frozen=True)
class Warning:
    """Non-fatal issue recorded in the workflow result."""

    code: str  # "VOICE_REFERENCE_MISSING"
    scope: str  # "locale:ar"
    message: Optional[str] = None


@dataclass(frozen=True)
class WorkflowResult:
    """Standard result envelope produced by every workflow on completion."""

    workflow_id: str
    run_id: str
    status: str  # one of WORKFLOW_STATUS_VALUES
    summary: Summary = field(default_factory=Summary)
    artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    catalog_refs: tuple[CatalogRef, ...] = field(default_factory=tuple)
    warnings: tuple[Warning, ...] = field(default_factory=tuple)
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in WORKFLOW_STATUS_VALUES:
            raise ValueError(
                f"Invalid workflow status {self.status!r}; "
                f"expected one of {sorted(WORKFLOW_STATUS_VALUES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "status": self.status,
            "summary": {
                "requested_items": self.summary.requested_items,
                "generated_items": self.summary.generated_items,
                "skipped_items": self.summary.skipped_items,
                "failed_items": self.summary.failed_items,
            },
            "artifacts": [
                {"kind": a.kind, "uri": a.uri, "checksum": a.checksum}
                for a in self.artifacts
            ],
            "catalog_refs": [
                {"system": c.system, "entity_type": c.entity_type, "entity_id": c.entity_id}
                for c in self.catalog_refs
            ],
            "warnings": [
                {"code": w.code, "scope": w.scope, "message": w.message}
                for w in self.warnings
            ],
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowResult":
        s = data.get("summary", {})
        return cls(
            workflow_id=data["workflow_id"],
            run_id=data["run_id"],
            status=data["status"],
            summary=Summary(
                requested_items=s.get("requested_items", 0),
                generated_items=s.get("generated_items", 0),
                skipped_items=s.get("skipped_items", 0),
                failed_items=s.get("failed_items", 0),
            ),
            artifacts=tuple(
                ArtifactRef(kind=a["kind"], uri=a["uri"], checksum=a["checksum"])
                for a in data.get("artifacts", [])
            ),
            catalog_refs=tuple(
                CatalogRef(
                    system=c["system"],
                    entity_type=c["entity_type"],
                    entity_id=c["entity_id"],
                )
                for c in data.get("catalog_refs", [])
            ),
            warnings=tuple(
                Warning(
                    code=w["code"],
                    scope=w["scope"],
                    message=w.get("message"),
                )
                for w in data.get("warnings", [])
            ),
            correlation_id=data.get("correlation_id"),
        )

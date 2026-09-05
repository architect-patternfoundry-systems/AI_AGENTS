"""Error taxonomy for cross-app workflow integration.

Standardized error codes that travel across app/activity boundaries.
See ADR-036 section on error taxonomy.

Every error includes a code, retryability, source, message, and optional
details reference. This gives every UI, workflow, and operator dashboard
the same vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Canonical error codes. Extend cautiously; each code implies a
# well-understood recovery or compensation behavior.
ERROR_CODES = frozenset(
    {
        "VALIDATION_FAILED",
        "AUTHORIZATION_DENIED",
        "APPROVAL_REJECTED",
        "APPROVAL_EXPIRED",
        "RESOURCE_UNAVAILABLE",
        "LEASE_NOT_ADMITTED",
        "DEPENDENCY_UNAVAILABLE",
        "RETRY_EXHAUSTED",
        "ARTIFACT_VALIDATION_FAILED",
        "ARTIFACT_PUBLICATION_FAILED",
        "CATALOG_REGISTRATION_FAILED",
        "CANCELLED",
        "COMPENSATION_FAILED",
        "INTERNAL_ERROR",
    }
)

# Default retryability per code. Activities and workflows may override
# based on context, but this is the baseline expectation.
_DEFAULT_RETRYABLE: dict[str, bool] = {
    "VALIDATION_FAILED": False,
    "AUTHORIZATION_DENIED": False,
    "APPROVAL_REJECTED": False,
    "APPROVAL_EXPIRED": False,
    "RESOURCE_UNAVAILABLE": True,
    "LEASE_NOT_ADMITTED": True,
    "DEPENDENCY_UNAVAILABLE": True,
    "RETRY_EXHAUSTED": False,
    "ARTIFACT_VALIDATION_FAILED": True,
    "ARTIFACT_PUBLICATION_FAILED": True,
    "CATALOG_REGISTRATION_FAILED": True,
    "CANCELLED": False,
    "COMPENSATION_FAILED": False,
    "INTERNAL_ERROR": True,
}


@dataclass(frozen=True)
class WorkflowError:
    """Standard error envelope that travels across app/activity boundaries.

    Carries enough information for a workflow to make a retry/compensation
    decision and for a UI to show a meaningful message without parsing
    implementation-specific exceptions.
    """

    code: str
    source: str  # e.g. "gpu-nanny", "alltalk-tts", "nexus", "cts"
    message: str
    retryable: bool = field(default=False)
    retry_after_seconds: Optional[int] = None
    details_ref: Optional[str] = None  # s3://.../failure-details.json
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.code not in ERROR_CODES:
            raise ValueError(
                f"Unknown error code {self.code!r}; "
                f"expected one of {sorted(ERROR_CODES)}"
            )
        # If retryable is not explicitly set, use the default for this code
        if not self.retryable and _DEFAULT_RETRYABLE.get(self.code, False):
            # Use object.__setattr__ because the dataclass is frozen
            object.__setattr__(self, "retryable", True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
            "source": self.source,
            "message": self.message,
            "details_ref": self.details_ref,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowError":
        return cls(
            code=data["code"],
            source=data["source"],
            message=data["message"],
            retryable=data.get("retryable", False),
            retry_after_seconds=data.get("retry_after_seconds"),
            details_ref=data.get("details_ref"),
            correlation_id=data.get("correlation_id"),
        )


# Convenience constructors for common error categories


def validation_failed(source: str, message: str, **kwargs: Any) -> WorkflowError:
    return WorkflowError(code="VALIDATION_FAILED", source=source, message=message, **kwargs)


def resource_unavailable(
    source: str, message: str, retry_after_seconds: int = 60, **kwargs: Any
) -> WorkflowError:
    return WorkflowError(
        code="RESOURCE_UNAVAILABLE",
        source=source,
        message=message,
        retry_after_seconds=retry_after_seconds,
        **kwargs,
    )


def dependency_unavailable(
    source: str, message: str, retry_after_seconds: int = 30, **kwargs: Any
) -> WorkflowError:
    return WorkflowError(
        code="DEPENDENCY_UNAVAILABLE",
        source=source,
        message=message,
        retry_after_seconds=retry_after_seconds,
        **kwargs,
    )


def retry_exhausted(source: str, message: str, **kwargs: Any) -> WorkflowError:
    return WorkflowError(code="RETRY_EXHAUSTED", source=source, message=message, **kwargs)


def internal_error(source: str, message: str, **kwargs: Any) -> WorkflowError:
    return WorkflowError(code="INTERNAL_ERROR", source=source, message=message, **kwargs)

"""Credential discovery, inventory, and enrollment contracts.

Implements the standard defined in ADR-038: Credential Discovery,
Inventory, and Enrollment Standard. These types maintain metadata and
fingerprints — never plaintext secret material.

The inventory record, discovery findings, capability assessment, and
enrollment plan are all secret-safe: they contain references, version
identifiers, and HMAC fingerprints, not credential values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .credential_rotation import (
    AutomationTracking,
    CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    CREDENTIAL_CLASS_OBJECT_STORAGE_KEY,
    CREDENTIAL_CLASS_API_KEY,
    LIFECYCLE_DISCOVERED,
    LIFECYCLE_BOOTSTRAP_REQUIRED,
    LIFECYCLE_ENROLLED,
    LIFECYCLE_ROTATION_READY,
    LIFECYCLE_AUTOMATICALLY_MANAGED,
    STRATEGY_DUAL_LOGIN_ROLE,
    STRATEGY_DYNAMIC_CREDENTIAL,
    STRATEGY_KEY_VERSION_ROTATION,
)


# --- Discovery source types ---

SOURCE_KUBERNETES = "kubernetes"
SOURCE_GIT = "git"
SOURCE_RUNTIME = "runtime"
SOURCE_PROVIDER = "provider"
SOURCE_TELEMETRY = "telemetry"
SOURCE_GITLEAKS = "gitleaks"

ALL_DISCOVERY_SOURCES = (
    SOURCE_KUBERNETES,
    SOURCE_GIT,
    SOURCE_RUNTIME,
    SOURCE_PROVIDER,
    SOURCE_TELEMETRY,
    SOURCE_GITLEAKS,
)

# --- Exposure status ---

EXPOSURE_UNKNOWN = "unknown"
EXPOSURE_CLEAN = "clean"
EXPOSURE_EXPOSED_ROTATED_PENDING_ENROLLMENT = "exposed_rotated_pending_enrollment"
EXPOSURE_EXPOSED_NOT_ROTATED = "exposed_not_rotated"
EXPOSURE_ROTATED_ENROLLED = "rotated_enrolled"

# --- Risk tiers ---

RISK_CRITICAL = "critical"
RISK_HIGH = "high"
RISK_MEDIUM = "medium"
RISK_LOW = "low"

ALL_RISK_TIERS = (RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM, RISK_LOW)

# --- Enrollment modes ---

ENROLLMENT_MODE_OBSERVE_ONLY = "observe_only"
ENROLLMENT_MODE_EXECUTE = "execute"

# --- Enrollment workflow steps ---

ENROLLMENT_STEPS = (
    "consolidate_discovery_evidence",
    "resolve_credential_set_identity",
    "infer_and_confirm_consumers",
    "assign_or_escalate_owner",
    "assess_risk_and_privilege",
    "assess_rotation_capabilities",
    "select_target_strategy",
    "generate_enrollment_plan",
    "await_approval",
    "create_scoped_successor_identity",
    "seed_external_secret_authority",
    "configure_secret_synchronization",
    "update_consumer_references",
    "validate_cutover_and_rollback",
    "register_rotation_policy",
    "mark_rotation_ready",
    "schedule_first_managed_rotation",
)


@dataclass(frozen=True)
class OwnerRef:
    """Identifies the accountable owner of a credential set."""

    team: str
    service: Optional[str] = None
    escalation_group: Optional[str] = None


@dataclass(frozen=True)
class AuthorityRef:
    """Reference to where a credential is stored — never the value."""

    provider: str  # "kubernetes_secret" | "vault" | "external_secrets" | "aws_secrets_manager"
    namespace: Optional[str] = None
    secret_name: Optional[str] = None
    key_names: tuple[str, ...] = ()
    external_secret_ref: Optional[str] = None


@dataclass(frozen=True)
class ConsumerRef:
    """A workload that consumes a credential."""

    kind: str  # "Deployment" | "StatefulSet" | "DaemonSet" | "Job" | "CronJob"
    namespace: str
    name: str
    container: Optional[str] = None
    env_var: Optional[str] = None
    reload_mode: Optional[str] = None  # "restart" | "sighup" | "file-watch" | "dynamic"


@dataclass(frozen=True)
class SourceFinding:
    """A redacted finding from a discovery scanner.

    Never contains the secret value. Contains only a location reference,
    scanner identity, severity, and an HMAC fingerprint.
    """

    scanner: str  # e.g. "gitleaks", "kubernetes-discovery", "git-history"
    location_ref: str  # e.g. "git:repo/path@commit:line" or "k8s:namespace/secret/name"
    severity: str = RISK_LOW  # one of ALL_RISK_TIERS
    confidence: str = "medium"  # "low" | "medium" | "high"
    secret_fingerprint: Optional[str] = None  # "hmac-sha256:..."
    plaintext_retained: bool = False


@dataclass(frozen=True)
class RiskAssessment:
    """Risk classification for a credential set."""

    tier: str = RISK_MEDIUM  # one of ALL_RISK_TIERS
    has_admin_privileges: bool = False
    exposure_status: str = EXPOSURE_UNKNOWN
    last_scanned_at: Optional[str] = None  # ISO timestamp
    secret_fingerprint: Optional[str] = None  # HMAC, never raw hash
    source_findings: tuple[SourceFinding, ...] = ()


@dataclass(frozen=True)
class RotationCapabilities:
    """Assessment of whether rotation is automatable for a credential set.

    Each capability is True only if the enrollment workflow verified
    that the corresponding adapter/probe/mechanism is available.
    """

    successor_creation: bool = False
    overlap_support: bool = False
    secret_authority: bool = False
    delivery: bool = False
    consumer_reload: bool = False
    positive_probe: bool = False
    predecessor_revocation: bool = False
    audit_observability: bool = False

    @property
    def rotation_ready(self) -> bool:
        """True if all required capabilities are present.

        audit_observability is recommended but not required for
        rotation_ready — it is required for automatically_managed.
        """
        return (
            self.successor_creation
            and self.overlap_support
            and self.secret_authority
            and self.delivery
            and self.consumer_reload
            and self.positive_probe
            and self.predecessor_revocation
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        """List of missing required capabilities."""
        missing = []
        if not self.successor_creation:
            missing.append("successor_creation")
        if not self.overlap_support:
            missing.append("overlap_support")
        if not self.secret_authority:
            missing.append("secret_authority")
        if not self.delivery:
            missing.append("delivery")
        if not self.consumer_reload:
            missing.append("consumer_reload")
        if not self.positive_probe:
            missing.append("positive_probe")
        if not self.predecessor_revocation:
            missing.append("predecessor_revocation")
        return tuple(missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "successor_creation": self.successor_creation,
            "overlap_support": self.overlap_support,
            "secret_authority": self.secret_authority,
            "delivery": self.delivery,
            "consumer_reload": self.consumer_reload,
            "positive_probe": self.positive_probe,
            "predecessor_revocation": self.predecessor_revocation,
            "audit_observability": self.audit_observability,
            "rotation_ready": self.rotation_ready,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class CredentialSetRecord:
    """Canonical inventory record for a credential set.

    Contains metadata and fingerprints — never plaintext secret material.
    This is the central record maintained by the Credential Inventory Service.
    """

    credential_set_id: str
    display_name: str
    credential_class: str  # e.g. "postgresql_login"
    environment: str  # e.g. "dev", "staging", "prod"
    lifecycle_state: str  # one of ALL_LIFECYCLE_STATES from ADR-037
    owner: Optional[OwnerRef] = None
    authority: Optional[AuthorityRef] = None
    consumers: tuple[ConsumerRef, ...] = ()
    risk: RiskAssessment = field(default_factory=RiskAssessment)
    capabilities: RotationCapabilities = field(default_factory=RotationCapabilities)
    target_strategy: Optional[str] = None  # e.g. "dual_login_role"
    current_mode: str = "static_unmanaged"
    target_mode: str = "automatically_managed"
    cadence_days: int = 30
    next_rotation_due_at: Optional[str] = None
    enrollment_deadline: Optional[str] = None
    evidence_refs: tuple[str, ...] = ()

    @property
    def is_unowned(self) -> bool:
        return self.owner is None

    @property
    def is_unmanaged(self) -> bool:
        return self.lifecycle_state in (
            LIFECYCLE_DISCOVERED,
            LIFECYCLE_BOOTSTRAP_REQUIRED,
        )

    @property
    def is_orphaned(self) -> bool:
        """A credential with a provider identity but no mapped consumers."""
        return len(self.consumers) == 0 and self.lifecycle_state != LIFECYCLE_DISCOVERED

    @property
    def is_shared_across_apps(self) -> bool:
        """A credential consumed by workloads in multiple namespaces."""
        if len(self.consumers) < 2:
            return False
        namespaces = {c.namespace for c in self.consumers}
        return len(namespaces) > 1


@dataclass(frozen=True)
class DiscoveryFinding:
    """A single observation from a discovery scanner.

    Produced by credential-discovery-agent and ingested into the
    inventory service. Never contains plaintext secret values.
    """

    finding_id: str
    source: str  # one of ALL_DISCOVERY_SOURCES
    detector: str  # e.g. "gitleaks", "k8s-secret-ref-scanner"
    location_ref: str  # provider-specific location reference
    rule_id: Optional[str] = None
    credential_class_hint: Optional[str] = None
    confidence: str = "medium"
    secret_fingerprint: Optional[str] = None  # HMAC, never raw hash
    plaintext_retained: bool = False
    consumer_hint: Optional[ConsumerRef] = None
    severity: str = RISK_LOW


@dataclass(frozen=True)
class EnrollmentPlan:
    """Structured plan for enrolling a credential set into managed rotation.

    Generated by the enrollment workflow in observe-only mode and
    executed in execute mode. Contains the target strategy, capability
    assessment, required steps, and blockers.
    """

    credential_set_id: str
    target_strategy: str
    capabilities: RotationCapabilities
    mode: str = ENROLLMENT_MODE_OBSERVE_ONLY  # "observe_only" | "execute"
    requires_approval: bool = False
    approval_reason: Optional[str] = None
    blockers: tuple[str, ...] = ()
    estimated_steps: tuple[str, ...] = ENROLLMENT_STEPS
    enrollment_deadline: Optional[str] = None

    @property
    def can_execute(self) -> bool:
        """True if the plan can proceed to execution.

        Requires execute mode, no blockers, and approval if required.
        """
        if self.mode != ENROLLMENT_MODE_EXECUTE:
            return False
        if self.blockers:
            return False
        if self.requires_approval:
            return False  # approval must be obtained separately
        return True


@dataclass(frozen=True)
class EnrollmentInput:
    """Secret-safe input for CredentialEnrollmentWorkflow v1.

    Never contains credential values. References the credential set
    and discovery findings by ID only.
    """

    credential_set_id: str
    mode: str = ENROLLMENT_MODE_OBSERVE_ONLY
    discovery_finding_ids: tuple[str, ...] = ()
    target_strategy: Optional[str] = None
    enrollment_deadline: Optional[str] = None
    correlation_id: Optional[str] = None
    contract_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "credential_set_id": self.credential_set_id,
            "mode": self.mode,
            "discovery_finding_ids": list(self.discovery_finding_ids),
            "target_strategy": self.target_strategy,
            "enrollment_deadline": self.enrollment_deadline,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True)
class EnrollmentResult:
    """Secret-safe result from CredentialEnrollmentWorkflow v1."""

    credential_set_id: str
    status: str  # "completed" | "observe_only_plan" | "blocked" | "failed" | "rolled_back"
    lifecycle_state: str  # resulting lifecycle state
    plan: Optional[EnrollmentPlan] = None
    capabilities: Optional[RotationCapabilities] = None
    correlation_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_set_id": self.credential_set_id,
            "status": self.status,
            "lifecycle_state": self.lifecycle_state,
            "plan": self.plan.__dict__ if self.plan else None,
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
            "correlation_id": self.correlation_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

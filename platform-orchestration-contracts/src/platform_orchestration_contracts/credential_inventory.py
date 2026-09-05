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

# --- Discovery workflow steps (Phase 1 controller) ---

DISCOVERY_STEPS = (
    "discover_kubernetes_references",
    "discover_external_secret_resources",
    "discover_postgres_roles",
    "discover_minio_accounts",
    "ingest_git_scanner_findings",
    "correlate_findings",
    "upsert_credential_inventory",
    "classify_risk_and_lifecycle",
    "detect_ownership_gaps",
    "emit_posture_metrics",
    "write_redacted_evidence_report",
)

# --- Exposure classification ---
#
# A secret in current runtime config and one in old Git history are
# different operational states. This prevents the dashboard from
# conflating remediated historical evidence with live exposure.

EXPOSURE_CLASS_ACTIVE_IN_SOURCE = "active_in_source"
EXPOSURE_CLASS_ACTIVE_IN_CLUSTER_NO_AUTHORITY = "active_in_cluster_no_authority"
EXPOSURE_CLASS_HISTORICAL_IDENTITY_VALID = "historical_identity_valid"
EXPOSURE_CLASS_HISTORICAL_REVOKED = "historical_revoked"
EXPOSURE_CLASS_PATTERN_ONLY = "pattern_only"
EXPOSURE_CLASS_TEST_FIXTURE = "test_fixture"

ALL_EXPOSURE_CLASSES = (
    EXPOSURE_CLASS_ACTIVE_IN_SOURCE,
    EXPOSURE_CLASS_ACTIVE_IN_CLUSTER_NO_AUTHORITY,
    EXPOSURE_CLASS_HISTORICAL_IDENTITY_VALID,
    EXPOSURE_CLASS_HISTORICAL_REVOKED,
    EXPOSURE_CLASS_PATTERN_ONLY,
    EXPOSURE_CLASS_TEST_FIXTURE,
)

# Default action by exposure class
EXPOSURE_DEFAULT_ACTIONS = {
    EXPOSURE_CLASS_ACTIVE_IN_SOURCE: "emergency_rotation",
    EXPOSURE_CLASS_ACTIVE_IN_CLUSTER_NO_AUTHORITY: "enroll_and_rotate",
    EXPOSURE_CLASS_HISTORICAL_IDENTITY_VALID: "rotate_and_revoke",
    EXPOSURE_CLASS_HISTORICAL_REVOKED: "retain_evidence_closed",
    EXPOSURE_CLASS_PATTERN_ONLY: "triage",
    EXPOSURE_CLASS_TEST_FIXTURE: "policy_dependent",
}

# --- Correlation confidence levels ---

CORRELATION_CONFIDENCE_HIGH = "high"
CORRELATION_CONFIDENCE_MEDIUM = "medium"
CORRELATION_CONFIDENCE_LOW = "low"

# Correlation matching basis — prioritize explicit annotations over inference
CORRELATION_BASIS_EXPLICIT_ANNOTATION = "explicit_annotation"
CORRELATION_BASIS_SECRET_AUTHORITY_PATH = "secret_authority_path"
CORRELATION_BASIS_PROVIDER_IDENTITY = "provider_identity"
CORRELATION_BASIS_FINGERPRINT_MATCH = "fingerprint_match"
CORRELATION_BASIS_NAME_INFERENCE = "name_inference"

# --- Exception reason codes ---

EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY = "provider_no_secondary_key"
EXCEPTION_REASON_LEGACY_SYSTEM_NO_API = "legacy_system_no_api"
EXCEPTION_REASON_VENDOR_LOCKED_CREDENTIAL = "vendor_locked_credential"
EXCEPTION_REASON_MIGRATION_IN_PROGRESS = "migration_in_progress"

# --- Data retention defaults ---

RETENTION_CRITICAL_DAYS = 2555  # ~7 years
RETENTION_HIGH_DAYS = 1095  # ~3 years
RETENTION_MEDIUM_DAYS = 365
RETENTION_LOW_DAYS = 90

RETENTION_BY_RISK_TIER = {
    RISK_CRITICAL: RETENTION_CRITICAL_DAYS,
    RISK_HIGH: RETENTION_HIGH_DAYS,
    RISK_MEDIUM: RETENTION_MEDIUM_DAYS,
    RISK_LOW: RETENTION_LOW_DAYS,
}


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
    owner_confirmation: bool = False
    rollback_verification: bool = False

    @property
    def rotation_ready(self) -> bool:
        """True if all base-tier required capabilities are present.

        This is the low-tier check. Use is_rotation_ready_for_risk for
        risk-tiered assessment.
        """
        return (
            self.successor_creation
            and self.secret_authority
            and self.delivery
            and self.consumer_reload
            and self.positive_probe
            and self.predecessor_revocation
        )

    def is_rotation_ready_for_risk(self, risk_tier: str) -> bool:
        """Risk-tiered **provider capability** readiness assessment.

        This evaluates whether the provider/infrastructure adapters can
        support rotation at the given risk tier. It does NOT evaluate
        workflow-level execution gates (approval policy, canary cutover,
        immutable evidence, emergency recovery) required for critical
        credentials. Use RotationExecutionGates for that.

        | Risk tier | Required provider capabilities |
        |---|---|
        | Low | successor, authority, delivery, reload, probe, revocation |
        | Medium | Low + overlap_support |
        | High | Medium + audit_observability, owner_confirmation, rollback_verification |
        | Critical | Same as High (workflow-level gates checked separately) |
        """
        if not self.rotation_ready:
            return False
        if risk_tier == RISK_LOW:
            return True
        if risk_tier == RISK_MEDIUM:
            return self.overlap_support
        if risk_tier in (RISK_HIGH, RISK_CRITICAL):
            return (
                self.overlap_support
                and self.audit_observability
                and self.owner_confirmation
                and self.rollback_verification
            )
        return False

    @property
    def blockers(self) -> tuple[str, ...]:
        """List of missing base-tier required capabilities."""
        missing = []
        if not self.successor_creation:
            missing.append("successor_creation")
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

    def blockers_for_risk(self, risk_tier: str) -> tuple[str, ...]:
        """List of missing capabilities for the given risk tier."""
        missing = list(self.blockers)
        if risk_tier in (RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL):
            if not self.overlap_support:
                missing.append("overlap_support")
        if risk_tier in (RISK_HIGH, RISK_CRITICAL):
            if not self.audit_observability:
                missing.append("audit_observability")
            if not self.owner_confirmation:
                missing.append("owner_confirmation")
            if not self.rollback_verification:
                missing.append("rollback_verification")
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
            "owner_confirmation": self.owner_confirmation,
            "rollback_verification": self.rollback_verification,
            "rotation_ready": self.rotation_ready,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class RotationExecutionGates:
    """Workflow-level execution gates for critical/admin credential rotation.

    These are distinct from provider capabilities (RotationCapabilities).
    A critical credential requires both provider-capability readiness
    AND execution-gate readiness before automated rotation may proceed.

    provider_ready = capabilities.is_rotation_ready_for_risk(RISK_CRITICAL)
    execution_ready = rotation_gates.critical_ready
    eligible = provider_ready and execution_ready
    """

    approval_policy_configured: bool = False
    canary_cutover_configured: bool = False
    immutable_evidence_store: bool = False
    emergency_recovery_plan_verified: bool = False

    @property
    def critical_ready(self) -> bool:
        """True if all critical-tier execution gates are configured."""
        return (
            self.approval_policy_configured
            and self.canary_cutover_configured
            and self.immutable_evidence_store
            and self.emergency_recovery_plan_verified
        )

    @property
    def missing_gates(self) -> tuple[str, ...]:
        """List of missing execution gates."""
        missing = []
        if not self.approval_policy_configured:
            missing.append("approval_policy_configured")
        if not self.canary_cutover_configured:
            missing.append("canary_cutover_configured")
        if not self.immutable_evidence_store:
            missing.append("immutable_evidence_store")
        if not self.emergency_recovery_plan_verified:
            missing.append("emergency_recovery_plan_verified")
        return tuple(missing)


@dataclass(frozen=True)
class RotationSubject:
    """The evaluated subject of a rotation eligibility decision.

    Captures the material configuration that the fingerprint must bind
    to: provider identity, secret-authority path, consumer set, rotation
    strategy, reload strategy, and approval/evidence references. If any
    of these change, the eligibility decision is stale and must be
    reevaluated.

    All references are opaque — no secret values, raw DSNs, or
    unredacted URLs. Use provider-native identifiers, paths, and
    version IDs only.
    """

    credential_set_id: str
    provider_ref: str  # e.g. "postgresql:infra-data-postgres"
    provider_identity_ref: str  # e.g. "role:cts_runtime_a"
    secret_authority_ref: str  # e.g. "vault:secret/cts/db#v3"
    consumer_set_ref: str  # e.g. "deployment:cts/cts-backend"
    consumer_set_version: str  # e.g. "resource_version:12345"
    rotation_strategy: str  # e.g. "dual_login_role"
    reload_strategy: str  # e.g. "rolling_restart"
    approval_policy_ref: Optional[str] = None  # e.g. "policy:high-risk-rotation"
    evidence_store_ref: Optional[str] = None  # e.g. "s3://security-evidence/..."

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_set_id": self.credential_set_id,
            "provider_ref": self.provider_ref,
            "provider_identity_ref": self.provider_identity_ref,
            "secret_authority_ref": self.secret_authority_ref,
            "consumer_set_ref": self.consumer_set_ref,
            "consumer_set_version": self.consumer_set_version,
            "rotation_strategy": self.rotation_strategy,
            "reload_strategy": self.reload_strategy,
            "approval_policy_ref": self.approval_policy_ref,
            "evidence_store_ref": self.evidence_store_ref,
        }


@dataclass(frozen=True)
class RotationEligibility:
    """Canonical rotation eligibility decision for a credential set.

    This is the authoritative output of evaluate_rotation_eligibility().
    It separates provider-capability readiness from workflow execution
    readiness so that a future controller or workflow cannot accidentally
    check only one dimension.

    Use this as the single input to:
    - CredentialEnrollmentWorkflow promotion decisions.
    - CredentialRotationWorkflow start checks.
    - CredentialSet.status.
    - Security dashboard posture reports.
    - Alerts describing why a credential is blocked.
    - Approval gates for high/critical credentials.

    The input_fingerprint binds this decision to the exact credential
    configuration and rotation plan it evaluated. The workflow should
    reevaluate if that fingerprint no longer matches because consumer
    workloads, provider identity, secret-authority path, rotation
    strategy, risk tier, or policy configuration changed.
    """

    credential_set_id: str
    risk_tier: str
    provider_ready: bool
    execution_ready: bool
    eligible: bool
    provider_blockers: tuple[str, ...]
    execution_blockers: tuple[str, ...]
    evaluated_at: str  # ISO timestamp, UTC, timezone-aware
    policy_version: str
    input_fingerprint: str  # sha256 of canonical JSON of evaluated inputs

    @property
    def all_blockers(self) -> tuple[str, ...]:
        """Combined and deduplicated provider and execution blockers."""
        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for b in self.provider_blockers + self.execution_blockers:
            if b not in seen:
                seen.add(b)
                result.append(b)
        return tuple(result)


class RotationBlocked(Exception):
    """Raised when a rotation is blocked by eligibility evaluation.

    This exception is the non-bypassable enforcement mechanism. The
    rotation worker should raise this when eligibility.eligible is False.
    Do not allow callers to pass force=True around this gate. Emergency
    rotation should be an explicit policy path that is itself audited
    and constrained — not a generic bypass.
    """

    def __init__(
        self,
        credential_set_id: str,
        blockers: tuple[str, ...],
        policy_version: str,
    ):
        self.credential_set_id = credential_set_id
        self.blockers = blockers
        self.policy_version = policy_version
        super().__init__(
            f"Rotation blocked for {credential_set_id} "
            f"(policy_version={policy_version}): {', '.join(blockers)}"
        )


@dataclass(frozen=True)
class WorkflowExecutionAuthorization:
    """Workflow-level execution authorization for a specific rotation.

    This is distinct from RotationEligibility (provider capability
    readiness). For high-tier credentials, eligibility.eligible means
    provider-ready, but the workflow must also obtain execution
    authorization before any mutation activity.

    The workflow must call both:
        provider_eligibility = evaluate_rotation_eligibility(...)
        execution_auth = evaluate_workflow_execution_authorization(...)

    And require both before mutation:
        if not provider_eligibility.eligible:
            raise RotationBlocked(...)
        if not execution_auth.authorized:
            raise RotationBlocked(...)

    Additionally, the subject_fingerprint must match the eligibility
    decision's input_fingerprint:
        if execution_auth.subject_fingerprint != eligibility.input_fingerprint:
            raise RotationBlocked(..., blockers=("subject_fingerprint_mismatch",))

    For critical-tier credentials, execution gates are already evaluated
    by evaluate_rotation_eligibility(). This authorization is an
    additional workflow-level check for high and critical tiers.

    Critical-tier gate precedence:

    1. Evaluate provider capability readiness (evaluate_rotation_eligibility).
    2. Evaluate critical platform execution gates (RotationExecutionGates,
       inside eligibility for critical tier).
    3. Evaluate workflow-specific execution authorization
       (evaluate_workflow_execution_authorization).
    4. Bind eligibility and authorization to the same subject/plan fingerprint.
    5. Only then invoke a provider mutation activity.
    6. Reevaluate after any material plan, identity, consumer, policy, or
       incident-state change.

    Do not construct this object directly in production code. Use
    evaluate_workflow_execution_authorization() so that `authorized` is
    derived from the execution checks, not caller-supplied.
    """

    credential_set_id: str
    risk_tier: str
    policy_version: str
    evaluated_at: str  # ISO timestamp

    # Execution checks (observable inputs — the evaluator derives authorized)
    immutable_evidence_sink_available: bool = False
    rollback_plan_validated: bool = False
    approval_requirement_resolved: bool = False
    cutover_scope_matches_approved_plan: bool = False
    no_active_incident_freeze: bool = False

    # Additional policy-level blockers not covered by the Boolean checks
    policy_blockers: tuple[str, ...] = ()

    # Fingerprint binding to the matching eligibility decision
    subject_fingerprint: str = ""  # must match eligibility.input_fingerprint
    execution_fingerprint: str = ""  # hash of execution-time inputs

    # Approval binding for high/critical rotations
    approval_ref: Optional[str] = None  # e.g. "approval:rotation_01J...:revision_3"
    approval_subject_fingerprint: Optional[str] = None  # must match subject_fingerprint
    approval_expires_at: Optional[str] = None  # ISO timestamp; None means unexpired check skipped

    @property
    def all_blockers(self) -> tuple[str, ...]:
        """All execution blockers — derived from checks plus policy blockers."""
        missing: list[str] = list(self.policy_blockers)
        if not self.immutable_evidence_sink_available:
            missing.append("immutable_evidence_sink_unavailable")
        if not self.rollback_plan_validated:
            missing.append("rollback_plan_not_validated")
        if not self.approval_requirement_resolved:
            missing.append("approval_requirement_unresolved")
        if not self.cutover_scope_matches_approved_plan:
            missing.append("cutover_scope_mismatch")
        if not self.no_active_incident_freeze:
            missing.append("active_incident_freeze")
        # Approval binding checks
        if self.approval_ref is not None:
            if self.approval_subject_fingerprint is not None:
                if self.approval_subject_fingerprint != self.subject_fingerprint:
                    missing.append("approval_subject_fingerprint_mismatch")
            if self.approval_expires_at is not None:
                from datetime import datetime, timezone
                try:
                    expiry = datetime.fromisoformat(self.approval_expires_at)
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    if expiry < now:
                        missing.append("approval_expired")
                except (ValueError, TypeError):
                    missing.append("approval_expiry_malformed")
        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for b in missing:
            if b not in seen:
                seen.add(b)
                result.append(b)
        return tuple(result)

    @property
    def authorized(self) -> bool:
        """True if all execution checks pass and no policy blockers exist.

        Derived from the execution checks, not caller-supplied. This
        prevents inconsistent instances where authorized=True but
        immutable_evidence_sink_available=False.
        """
        return len(self.all_blockers) == 0

    def matches_eligibility(self, eligibility: "RotationEligibility") -> bool:
        """True if this authorization is bound to the given eligibility decision.

        The subject_fingerprint must match the eligibility's input_fingerprint.
        This prevents reusing an authorization after material conditions change.
        """
        return self.subject_fingerprint == eligibility.input_fingerprint


# Valid risk tiers for input validation
_VALID_RISK_TIERS = frozenset(ALL_RISK_TIERS)

# Valid credential_set_id grammar: lowercase alphanumeric, hyphens, underscores
import re as _re
_CREDENTIAL_SET_ID_PATTERN = _re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _compute_input_fingerprint(
    *,
    subject: RotationSubject,
    risk_tier: str,
    capabilities: RotationCapabilities,
    gates: Optional[RotationExecutionGates],
    policy_version: str,
) -> str:
    """Compute a SHA-256 fingerprint binding the decision to its inputs.

    The fingerprint covers the full RotationSubject (provider identity,
    secret-authority path, consumer set, rotation strategy, reload
    strategy, approval/evidence refs) plus risk tier, capabilities,
    gates, and policy version.

    The workflow should reevaluate eligibility if this fingerprint no
    longer matches because material conditions changed.
    """
    import hashlib
    import json

    payload = {
        "subject": subject.to_dict(),
        "risk_tier": risk_tier,
        "capabilities": capabilities.to_dict(),
        "gates": {
            "approval_policy_configured": gates.approval_policy_configured,
            "canary_cutover_configured": gates.canary_cutover_configured,
            "immutable_evidence_store": gates.immutable_evidence_store,
            "emergency_recovery_plan_verified": gates.emergency_recovery_plan_verified,
        } if gates else None,
        "policy_version": policy_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_eligibility_inputs(
    *,
    credential_set_id: str,
    risk_tier: str,
    policy_version: str,
) -> None:
    """Validate inputs to evaluate_rotation_eligibility.

    Raises ValueError with a descriptive message for invalid inputs.
    Structured validation is clearer and safer than silently treating
    malformed policy input as an ineligible state.
    """
    if not credential_set_id or not _CREDENTIAL_SET_ID_PATTERN.match(credential_set_id):
        raise ValueError(
            f"credential_set_id must match [a-z0-9][a-z0-9_-]*, got: {credential_set_id!r}"
        )
    if risk_tier not in _VALID_RISK_TIERS:
        raise ValueError(
            f"risk_tier must be one of {sorted(_VALID_RISK_TIERS)}, got: {risk_tier!r}"
        )
    if not policy_version:
        raise ValueError("policy_version must be non-empty")


def evaluate_rotation_eligibility(
    *,
    subject: RotationSubject,
    risk_tier: str,
    capabilities: RotationCapabilities,
    gates: Optional[RotationExecutionGates] = None,
    policy_version: str = "1",
) -> RotationEligibility:
    """Evaluate whether a credential set is eligible for rotation.

    This is the canonical policy-evaluation function. All consumers
    (enrollment workflow, rotation workflow, CRD status, dashboards)
    should call this rather than implementing their own readiness check.

    The subject parameter binds the decision to the exact provider
    identity, secret-authority path, consumer set, rotation strategy,
    and reload strategy under evaluation. If any of these change, the
    input_fingerprint will differ, signaling that the decision is stale.

    Policy on execution gates by tier:

    | Tier | Provider capability requirements | Execution gate requirements |
    |---|---|---|
    | Low | Base 6 capabilities | None beyond standard workflow execution |
    | Medium | Base + overlap | None beyond standard workflow execution |
    | High | Base + overlap + audit/owner/rollback | Not evaluated by this function. High-tier execution controls (immutable evidence, rollback verification, policy-defined approval) are enforced by the workflow policy at start time via WorkflowExecutionAuthorization. This is intentional: high-tier eligibility means provider-ready, while execution gating is a workflow-level concern. |
    | Critical | Same as High | Full critical gates required: approval policy, canary cutover, immutable evidence, emergency recovery. gates=None is treated as not eligible. WorkflowExecutionAuthorization is also required. |

    For high and critical tiers, the workflow must obtain BOTH:
        provider_eligibility = evaluate_rotation_eligibility(...)
        execution_authorization = evaluate_workflow_execution_policy(...)
    And require both before any mutation activity.

    Note: approval_policy_configured=True means the system knows when
    and how approval is required — it does NOT mean an approval has been
    granted for a particular rotation. The workflow must separately
    track the actual approval signal.

    Raises:
        ValueError: If risk_tier is not a recognized tier, subject
            credential_set_id does not match the identifier grammar,
            or policy_version is empty.
    """
    _validate_eligibility_inputs(
        credential_set_id=subject.credential_set_id,
        risk_tier=risk_tier,
        policy_version=policy_version,
    )

    provider_ready = capabilities.is_rotation_ready_for_risk(risk_tier)
    provider_blockers = capabilities.blockers_for_risk(risk_tier)

    if risk_tier == RISK_CRITICAL:
        if gates is None:
            execution_ready = False
            execution_blockers = ("rotation_execution_gates_missing",)
        else:
            execution_ready = gates.critical_ready
            execution_blockers = gates.missing_gates
    else:
        # High-tier and below: execution gates are intentionally not
        # evaluated here. High-tier execution controls (immutable evidence,
        # rollback verification, approval) are enforced by the workflow
        # policy at start time via WorkflowExecutionAuthorization.
        execution_ready = True
        execution_blockers = ()

    fingerprint = _compute_input_fingerprint(
        subject=subject,
        risk_tier=risk_tier,
        capabilities=capabilities,
        gates=gates,
        policy_version=policy_version,
    )

    return RotationEligibility(
        credential_set_id=subject.credential_set_id,
        risk_tier=risk_tier,
        provider_ready=provider_ready,
        execution_ready=execution_ready,
        eligible=provider_ready and execution_ready,
        provider_blockers=provider_blockers,
        execution_blockers=execution_blockers,
        evaluated_at=_utc_now_iso(),
        policy_version=policy_version,
        input_fingerprint=fingerprint,
    )


def _compute_execution_fingerprint(
    *,
    subject_fingerprint: str,
    immutable_evidence_sink_available: bool,
    rollback_plan_validated: bool,
    approval_requirement_resolved: bool,
    cutover_scope_matches_approved_plan: bool,
    no_active_incident_freeze: bool,
    policy_blockers: tuple[str, ...],
    policy_version: str,
) -> str:
    """Compute a SHA-256 fingerprint over execution-time inputs.

    This binds the authorization to the exact execution conditions it
    evaluated. If approval state, incident freeze, cutover scope, or
    evidence sink availability changes, the fingerprint differs.
    """
    import hashlib
    import json

    payload = {
        "subject_fingerprint": subject_fingerprint,
        "immutable_evidence_sink_available": immutable_evidence_sink_available,
        "rollback_plan_validated": rollback_plan_validated,
        "approval_requirement_resolved": approval_requirement_resolved,
        "cutover_scope_matches_approved_plan": cutover_scope_matches_approved_plan,
        "no_active_incident_freeze": no_active_incident_freeze,
        "policy_blockers": list(policy_blockers),
        "policy_version": policy_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_workflow_execution_authorization(
    *,
    subject: RotationSubject,
    risk_tier: str,
    eligibility: RotationEligibility,
    immutable_evidence_sink_available: bool,
    rollback_plan_validated: bool,
    approval_requirement_resolved: bool,
    cutover_scope_matches_approved_plan: bool,
    no_active_incident_freeze: bool,
    policy_blockers: tuple[str, ...] = (),
    policy_version: str = "1",
    approval_ref: Optional[str] = None,
    approval_subject_fingerprint: Optional[str] = None,
    approval_expires_at: Optional[str] = None,
) -> WorkflowExecutionAuthorization:
    """Evaluate workflow-level execution authorization for a rotation.

    This is the canonical evaluator for workflow execution authorization.
    Callers supply observable execution-time inputs; the library derives
    the `authorized` decision. Do not construct
    WorkflowExecutionAuthorization directly in production code.

    The eligibility parameter binds this authorization to a specific
    eligibility decision via subject_fingerprint. The evaluator
    fail-fast validates that subject, risk_tier, and policy_version
    are consistent with the eligibility decision. The workflow must
    also verify execution_auth.matches_eligibility(eligibility) before
    proceeding to mutation.

    For high/critical rotations, supply approval_ref,
    approval_subject_fingerprint, and approval_expires_at to bind the
    authorization to a specific approval. The evaluator checks that the
    approval's subject fingerprint matches the current subject
    fingerprint and that the approval has not expired.

    Precedence for critical-tier rotations:
    1. evaluate_rotation_eligibility (provider caps + critical gates)
    2. evaluate_workflow_execution_authorization (this function)
    3. Verify fingerprint binding
    4. Only then invoke provider mutation

    Raises:
        ValueError: If risk_tier is invalid, credential_set_id is
            malformed, policy_version is empty, or subject/risk_tier/
            policy_version do not match the supplied eligibility.
    """
    _validate_eligibility_inputs(
        credential_set_id=subject.credential_set_id,
        risk_tier=risk_tier,
        policy_version=policy_version,
    )

    # Fail-fast: subject, risk_tier, and policy_version must match eligibility
    if subject.credential_set_id != eligibility.credential_set_id:
        raise ValueError(
            f"subject credential_set_id ({subject.credential_set_id!r}) "
            f"does not match eligibility ({eligibility.credential_set_id!r})"
        )
    if risk_tier != eligibility.risk_tier:
        raise ValueError(
            f"risk_tier ({risk_tier!r}) does not match eligibility "
            f"({eligibility.risk_tier!r})"
        )
    if policy_version != eligibility.policy_version:
        raise ValueError(
            f"policy_version ({policy_version!r}) does not match eligibility "
            f"({eligibility.policy_version!r})"
        )

    exec_fp = _compute_execution_fingerprint(
        subject_fingerprint=eligibility.input_fingerprint,
        immutable_evidence_sink_available=immutable_evidence_sink_available,
        rollback_plan_validated=rollback_plan_validated,
        approval_requirement_resolved=approval_requirement_resolved,
        cutover_scope_matches_approved_plan=cutover_scope_matches_approved_plan,
        no_active_incident_freeze=no_active_incident_freeze,
        policy_blockers=policy_blockers,
        policy_version=policy_version,
    )

    return WorkflowExecutionAuthorization(
        credential_set_id=subject.credential_set_id,
        risk_tier=risk_tier,
        policy_version=policy_version,
        evaluated_at=_utc_now_iso(),
        immutable_evidence_sink_available=immutable_evidence_sink_available,
        rollback_plan_validated=rollback_plan_validated,
        approval_requirement_resolved=approval_requirement_resolved,
        cutover_scope_matches_approved_plan=cutover_scope_matches_approved_plan,
        no_active_incident_freeze=no_active_incident_freeze,
        policy_blockers=policy_blockers,
        subject_fingerprint=eligibility.input_fingerprint,
        execution_fingerprint=exec_fp,
        approval_ref=approval_ref,
        approval_subject_fingerprint=approval_subject_fingerprint,
        approval_expires_at=approval_expires_at,
    )


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


@dataclass(frozen=True)
class CorrelationEvidence:
    """Evidence linking a discovery finding to a credential set.

    Used by the correlation service to deduplicate observations from
    multiple scanners into a single CredentialSetRecord. Prioritizes
    explicit annotations over inference.
    """

    finding_type: str  # e.g. "kubernetes_consumer", "postgres_role", "git_finding"
    confidence: str  # "high" | "medium" | "low"
    matching_basis: str  # one of CORRELATION_BASIS_* constants
    finding_ref: Optional[str] = None  # reference to the source finding


@dataclass(frozen=True)
class CredentialCorrelation:
    """Result of correlating multiple findings into one credential set.

    Do not merge records only by secret name, role name, or an unkeyed
    fingerprint. Use confidence-based correlation with explicit
    annotations prioritized over inference.
    """

    canonical_credential_set_id: str
    evidence: tuple[CorrelationEvidence, ...]
    confirmed: bool = False  # True only after owner or policy resolves ambiguity

    @property
    def highest_confidence(self) -> Optional[str]:
        """Returns the highest confidence level across all evidence.

        Returns None if there is no evidence. This distinguishes "no
        evidence" from "low-confidence evidence" — an empty-evidence
        credential set should become an explicit integrity alert,
        not a low-confidence inference.
        """
        if not self.evidence:
            return None
        if any(e.confidence == CORRELATION_CONFIDENCE_HIGH for e in self.evidence):
            return CORRELATION_CONFIDENCE_HIGH
        if any(e.confidence == CORRELATION_CONFIDENCE_MEDIUM for e in self.evidence):
            return CORRELATION_CONFIDENCE_MEDIUM
        return CORRELATION_CONFIDENCE_LOW

    @property
    def has_evidence(self) -> bool:
        """True if any evidence exists for this correlation."""
        return bool(self.evidence)

    @property
    def has_explicit_annotation(self) -> bool:
        """True if any evidence is based on explicit workload annotation."""
        return any(
            e.matching_basis == CORRELATION_BASIS_EXPLICIT_ANNOTATION
            for e in self.evidence
        )


@dataclass(frozen=True)
class CredentialException:
    """A formally approved exception allowing a credential to remain
    in a non-automatically-managed state with expiry.

    The governing rule permits credentials to be "explicitly excepted
    with expiry." This record defines that exception fully. A scheduled
    controller should alert before expiry and reopen enrollment
    automatically if the exception is not renewed.
    """

    exception_id: str
    credential_set_id: str
    reason_code: str  # one of EXCEPTION_REASON_* constants
    risk_accepted_by: str  # name/identity of approver
    approved_at: str  # ISO timestamp
    expires_at: str  # ISO timestamp
    compensating_controls: tuple[str, ...] = ()
    remediation_target: Optional[str] = None  # e.g. "migrate-to-provider-x"

    @property
    def is_expired(self) -> bool:
        """True if the exception has passed its expiry.

        Fails CLOSED on malformed or missing expiry dates: an invalid
        expiry is treated as expired, not as valid. This prevents a
        malformed exception from silently granting perpetual unmanaged
        status.
        """
        from datetime import datetime
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return True
        return datetime.now(expiry.tzinfo) >= expiry

    @property
    def is_valid(self) -> bool:
        """True if the exception has a parseable expiry and a remediation target.

        A valid exception has:
        - A parseable expires_at timestamp.
        - A non-empty remediation_target (no permanent exceptions).
        """
        from datetime import datetime
        try:
            datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return False
        return bool(self.remediation_target)


@dataclass(frozen=True)
class InventoryRetentionPolicy:
    """Data retention rules for the credential inventory.

    The inventory contains security-sensitive metadata even without
    secret values. An attacker who knows every secret path, namespace,
    privileged role, and workload dependency graph has valuable
    reconnaissance material.
    """

    retention_days_by_risk: dict[str, int] = field(default_factory=lambda: dict(RETENTION_BY_RISK_TIER))
    encrypt_at_rest: bool = True
    access_control_enabled: bool = True
    raw_shell_history_ingestion: bool = False  # opt-in only
    archive_on_retire: bool = True

    def retention_days_for(self, risk_tier: str) -> int:
        """Returns the retention period in days for the given risk tier."""
        return self.retention_days_by_risk.get(risk_tier, RETENTION_LOW_DAYS)

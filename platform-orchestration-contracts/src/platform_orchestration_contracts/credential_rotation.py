"""Credential rotation lifecycle contracts.

Secret-safe input and result types for the CredentialRotationWorkflow v1
defined in ADR-037. These types never contain credential values — only
opaque references, version identifiers, and verification results.

See ADR-037 for the full workflow design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# --- Credential classes ---

CREDENTIAL_CLASS_POSTGRESQL_LOGIN = "postgresql_login"
CREDENTIAL_CLASS_OBJECT_STORAGE_KEY = "object_storage_key"
CREDENTIAL_CLASS_API_KEY = "api_key"
CREDENTIAL_CLASS_TLS_CERTIFICATE = "tls_certificate"
CREDENTIAL_CLASS_ENCRYPTION_KEY = "encryption_key"

# --- Rotation strategies ---

STRATEGY_DUAL_LOGIN_ROLE = "dual_login_role"
STRATEGY_DYNAMIC_CREDENTIAL = "dynamic_credential"
STRATEGY_KEY_VERSION_ROTATION = "key_version_rotation"
STRATEGY_CERTIFICATE_RENEWAL = "certificate_renewal"

# --- Rotation triggers ---

TRIGGER_SCHEDULED = "scheduled"
TRIGGER_EXPOSURE = "exposure"
TRIGGER_PERSONNEL_CHANGE = "personnel_change"
TRIGGER_SUSPICIOUS_AUTH = "suspicious_auth"
TRIGGER_INFRASTRUCTURE_CHANGE = "infrastructure_change"
TRIGGER_MANUAL = "manual"

# --- Workflow step names (for metrics and evidence) ---

ROTATION_STEPS = (
    "load_rotation_policy",
    "acquire_rotation_lock",
    "inventory_consumers",
    "create_successor_credential",
    "store_candidate_secret_version",
    "synchronize_kubernetes_secret",
    "roll_or_reload_consumers",
    "verify_consumer_health",
    "verify_real_dependency_operation",
    "await_grace_and_drain_period",
    "revoke_predecessor_credential",
    "verify_revocation",
    "write_rotation_evidence",
    "notify_security_and_owners",
)

# --- Verification check names ---

VERIFICATION_WORKLOAD_READY = "workload_ready"
VERIFICATION_DATABASE_CONNECTIVITY = "database_connectivity"
VERIFICATION_READ_WRITE_PROBE = "read_write_probe"
VERIFICATION_OBJECT_STORAGE_ACCESS = "object_storage_access"
VERIFICATION_OLD_CREDENTIAL_REJECTED = "old_credential_rejected"


@dataclass(frozen=True)
class SecretRef:
    """Opaque reference to a secret stored in a secret authority.

    Never contains the secret value. Identifies the provider, path, and
    version so the workflow can refer to credentials without embedding
    them in workflow history.
    """

    provider: str  # "vault" | "external-secrets" | "kubernetes-secret" | "aws-secrets-manager"
    path: str  # provider-specific path/identifier
    current_version: Optional[str] = None  # e.g. "v17"


@dataclass(frozen=True)
class ConsumerSelector:
    """Selects which Kubernetes workloads consume the credential being rotated."""

    namespace: str
    workloads: tuple[str, ...]


@dataclass(frozen=True)
class RotationInput:
    """Secret-safe input for CredentialRotationWorkflow v1.

    Never contains credential values. Uses opaque references to a secret
    authority so that workflow history, logs, and audit records contain
    only version identifiers and metadata.
    """

    credential_set_id: str  # e.g. "cts-postgres-runtime"
    credential_class: str  # e.g. "postgresql_login"
    secret_ref: SecretRef
    rotation_policy_id: str  # e.g. "service-db-standard-v1"
    consumer_selector: ConsumerSelector
    strategy: str  # e.g. "dual_login_role"
    trigger: str = TRIGGER_SCHEDULED
    correlation_id: Optional[str] = None
    contract_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "credential_set_id": self.credential_set_id,
            "credential_class": self.credential_class,
            "secret_ref": {
                "provider": self.secret_ref.provider,
                "path": self.secret_ref.path,
                "current_version": self.secret_ref.current_version,
            },
            "rotation_policy_id": self.rotation_policy_id,
            "consumer_selector": {
                "namespace": self.consumer_selector.namespace,
                "workloads": list(self.consumer_selector.workloads),
            },
            "strategy": self.strategy,
            "trigger": self.trigger,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RotationInput":
        sr = data["secret_ref"]
        cs = data["consumer_selector"]
        return cls(
            contract_version=data.get("contract_version", "1.0"),
            credential_set_id=data["credential_set_id"],
            credential_class=data["credential_class"],
            secret_ref=SecretRef(
                provider=sr["provider"],
                path=sr["path"],
                current_version=sr.get("current_version"),
            ),
            rotation_policy_id=data["rotation_policy_id"],
            consumer_selector=ConsumerSelector(
                namespace=cs["namespace"],
                workloads=tuple(cs["workloads"]),
            ),
            strategy=data["strategy"],
            trigger=data.get("trigger", TRIGGER_SCHEDULED),
            correlation_id=data.get("correlation_id"),
        )


@dataclass(frozen=True)
class RotationVerification:
    """Verification results from a rotation workflow.

    Each field records whether a specific verification check passed.
    Uses Optional[bool] where None means "not run", True means "passed",
    and False means "run and failed". all_passed returns True only if
    every check that was run returned True.
    """

    workload_ready: Optional[bool] = None
    database_connectivity: Optional[bool] = None
    read_write_probe: Optional[bool] = None
    object_storage_access: Optional[bool] = None
    old_credential_revoked: Optional[bool] = None

    @property
    def all_passed(self) -> bool:
        """True if all verification checks that were run passed.

        A check that was not run (None) does not affect the result.
        A check that was run and failed (False) makes this False.
        """
        checks = [
            self.workload_ready,
            self.database_connectivity,
            self.read_write_probe,
            self.object_storage_access,
            self.old_credential_revoked,
        ]
        # A check that was run (not None) must be True
        return all(c is None or c is True for c in checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workload_ready": self.workload_ready,
            "database_connectivity": self.database_connectivity,
            "read_write_probe": self.read_write_probe,
            "object_storage_access": self.object_storage_access,
            "old_credential_revoked": self.old_credential_revoked,
        }


@dataclass(frozen=True)
class RotationResult:
    """Secret-safe result from CredentialRotationWorkflow v1.

    References versions and identities — never credential values.
    """

    credential_set_id: str
    status: str  # "completed" | "failed" | "rolled_back" | "in_progress"
    previous_version: Optional[str] = None
    active_version: Optional[str] = None
    previous_identity: Optional[str] = None  # e.g. "cts_runtime_a"
    active_identity: Optional[str] = None  # e.g. "cts_runtime_b"
    verification: RotationVerification = field(default_factory=RotationVerification)
    correlation_id: Optional[str] = None
    error_code: Optional[str] = None  # from ADR-036 error taxonomy
    error_message: Optional[str] = None  # human-readable, no secrets

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_set_id": self.credential_set_id,
            "status": self.status,
            "previous_version": self.previous_version,
            "active_version": self.active_version,
            "previous_identity": self.previous_identity,
            "active_identity": self.active_identity,
            "verification": self.verification.to_dict(),
            "correlation_id": self.correlation_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class RotationPolicy:
    """Declarative rotation policy for a credential set.

    Loaded by the first workflow step (LoadRotationPolicy) to determine
    strategy, cadence, grace period, and verification requirements.
    """

    credential_set: str
    credential_type: str  # e.g. "postgresql_login"
    owner: str
    rotation_mode: str = STRATEGY_DUAL_LOGIN_ROLE
    cadence_days: int = 30
    grace_period_minutes: int = 30
    max_rotation_duration_minutes: int = 45
    require_approval: bool = False
    emergency_triggers: tuple[str, ...] = (
        TRIGGER_EXPOSURE,
        TRIGGER_SUSPICIOUS_AUTH,
    )
    verification_checks: tuple[str, ...] = (
        VERIFICATION_WORKLOAD_READY,
        VERIFICATION_OLD_CREDENTIAL_REJECTED,
    )
    rollback_allowed_before_revocation: bool = True


@dataclass(frozen=True)
class RotationLock:
    """Distributed lock state for credential rotation.

    Ensures only one active rotation per credential set.
    """

    credential_set_id: str
    rotation_generation: int
    state: str  # "rotating" | "completed" | "failed" | "expired"
    lock_owner_workflow_id: str
    lock_expires_at: str  # ISO timestamp

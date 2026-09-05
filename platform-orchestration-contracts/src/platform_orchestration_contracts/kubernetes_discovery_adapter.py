"""Kubernetes metadata discovery adapter — Phase 1 read-only.

Discovers credential references in Kubernetes workload metadata without
reading Secret.data. The adapter examines:

- Deployment, StatefulSet, DaemonSet, Job, CronJob env var references
- envFrom secretRef blocks
- volumes.secret references
- ExternalSecret and SecretStore/ClusterSecretStore resources
- ServiceAccount annotations (for workload identity hints)

The adapter NEVER reads Secret.data. It only reads workload resource
metadata to identify which workloads reference which secrets and how
credentials are delivered (env var, envFrom, volume mount).

Required RBAC for the adapter service account:
    get/list/watch:
      deployments, statefulsets, daemonsets, jobs, cronjobs
      configmaps (only if used for secret source references)
      externalsecrets, secretstores, clustersecretstores
      serviceaccounts
    secrets: NOT REQUIRED — do not grant Secret data read

The adapter uses a pluggable client interface so it can be tested with
synthetic data or connected to a real Kubernetes API server.

Output: tuple[CredentialObservation, ...] with source="kubernetes".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from .credential_discovery_workflow import (
    CredentialObservation,
    COVERAGE_SOURCE_KUBERNETES,
)
from .credential_inventory import ConsumerRef, OwnerRef
from .credential_rotation import (
    CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    CREDENTIAL_CLASS_OBJECT_STORAGE_KEY,
    CREDENTIAL_CLASS_API_KEY,
)
from .observation_safety import assert_observation_safe, UnsafeObservationError


# --- Risk signals emitted by the Kubernetes adapter ---

RISK_SIGNAL_K8S_SECRET_DELIVERY = "credential-delivered-through-kubernetes-secret"
RISK_SIGNAL_INLINE_ENV_SECRET = "credential-inlined-in-env-var"
RISK_SIGNAL_RUNTIME_DB_ACCESS = "runtime-database-access"
RISK_SIGNAL_OBJECT_STORAGE_ACCESS = "object-storage-access"
RISK_SIGNAL_EXTERNAL_SECRET_REF = "credential-managed-via-external-secrets"
RISK_SIGNAL_SHARED_SECRET_ACROSS_NAMESPACES = "shared-secret-across-namespaces"
RISK_SIGNAL_NO_SECRET_REF = "credential-env-var-without-secret-reference"

# Env var name → credential class mapping (heuristic, not authoritative)
_ENV_VAR_CREDENTIAL_CLASS_MAP: dict[str, str] = {
    "POSTGRES_DSN": CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    "POSTGRES_URL": CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    "DATABASE_URL": CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    "DB_DSN": CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    "PG_DSN": CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    "AWS_SECRET_ACCESS_KEY": CREDENTIAL_CLASS_OBJECT_STORAGE_KEY,
    "MINIO_SECRET_KEY": CREDENTIAL_CLASS_OBJECT_STORAGE_KEY,
    "S3_SECRET_ACCESS_KEY": CREDENTIAL_CLASS_OBJECT_STORAGE_KEY,
    "API_KEY": CREDENTIAL_CLASS_API_KEY,
    "AUTH_TOKEN": CREDENTIAL_CLASS_API_KEY,
    "BEARER_TOKEN": CREDENTIAL_CLASS_API_KEY,
}

# Env var names that indicate credential usage (for risk signal classification)
_DB_ENV_VAR_PATTERNS = ("POSTGRES", "DATABASE", "DB_", "PG_", "MYSQL", "REDIS")
_STORAGE_ENV_VAR_PATTERNS = ("AWS_", "MINIO", "S3_", "STORAGE")


def _infer_credential_class(env_var_name: str) -> Optional[str]:
    """Infer credential class from env var name. Returns None if not a credential."""
    upper = env_var_name.upper()
    if upper in _ENV_VAR_CREDENTIAL_CLASS_MAP:
        return _ENV_VAR_CREDENTIAL_CLASS_MAP[upper]
    # Heuristic: check patterns
    if any(p in upper for p in _DB_ENV_VAR_PATTERNS):
        if "DSN" in upper or "URL" in upper or "PASSWORD" in upper or "PASS" in upper:
            return CREDENTIAL_CLASS_POSTGRESQL_LOGIN
    if any(p in upper for p in _STORAGE_ENV_VAR_PATTERNS):
        if "SECRET" in upper or "KEY" in upper or "PASSWORD" in upper:
            return CREDENTIAL_CLASS_OBJECT_STORAGE_KEY
    if "API_KEY" in upper or "AUTH_TOKEN" in upper or "BEARER" in upper:
        return CREDENTIAL_CLASS_API_KEY
    return None


def _is_credential_env_var(env_var_name: str) -> bool:
    """Check if an env var name is likely a credential reference."""
    return _infer_credential_class(env_var_name) is not None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Pluggable client interface ---


@dataclass(frozen=True)
class WorkloadEnvVar:
    """A single env var from a workload, with optional secret reference."""

    name: str
    value: Optional[str] = None  # inline value — adapter NEVER propagates this
    secret_ref_name: Optional[str] = None  # Secret name if from secretKeyRef
    secret_ref_key: Optional[str] = None  # key within the Secret


@dataclass(frozen=True)
class WorkloadEnvFrom:
    """An envFrom block that pulls all keys from a Secret."""

    secret_ref_name: str
    optional: bool = False


@dataclass(frozen=True)
class WorkloadVolumeSecret:
    """A volume mounted from a Secret."""

    volume_name: str
    secret_ref_name: str
    mount_path: Optional[str] = None


@dataclass(frozen=True)
class WorkloadMetadata:
    """Metadata for a single Kubernetes workload, extracted by the client.

    The adapter client is responsible for extracting this from the API
    server. The adapter itself never touches the Kubernetes API directly.
    This abstraction makes the adapter testable with synthetic data.
    """

    kind: str  # "Deployment" | "StatefulSet" | "DaemonSet" | "Job" | "CronJob"
    namespace: str
    name: str
    container_name: Optional[str] = None
    env_vars: tuple[WorkloadEnvVar, ...] = ()
    env_from: tuple[WorkloadEnvFrom, ...] = ()
    volume_secrets: tuple[WorkloadVolumeSecret, ...] = ()
    service_account: Optional[str] = None
    owner_annotations: dict[str, str] = field(default_factory=dict)
    resource_version: Optional[str] = None


@dataclass(frozen=True)
class ExternalSecretMetadata:
    """Metadata for an ExternalSecret resource (without target Secret data)."""

    namespace: str
    name: str
    secret_store_ref: Optional[str] = None
    secret_store_kind: Optional[str] = None  # "SecretStore" | "ClusterSecretStore"
    remote_ref_keys: tuple[str, ...] = ()  # key names only, not values
    target_secret_name: Optional[str] = None
    resource_version: Optional[str] = None


class KubernetesDiscoveryClient(Protocol):
    """Protocol for Kubernetes API clients used by the discovery adapter.

    Implementations must NEVER return Secret.data. They return only
    workload metadata and ExternalSecret/SecretStore metadata.

    A real implementation would use the Kubernetes Python client library.
    A test implementation returns synthetic WorkloadMetadata tuples.
    """

    def list_workloads(self, namespace: str) -> tuple[WorkloadMetadata, ...]:
        """List workload metadata (Deployments, StatefulSets, etc.) in a namespace."""
        ...

    def list_external_secrets(self, namespace: str) -> tuple[ExternalSecretMetadata, ...]:
        """List ExternalSecret metadata in a namespace."""
        ...


# --- Owner hint extraction ---


def _extract_owner_hint(
    workload: WorkloadMetadata,
) -> Optional[OwnerRef]:
    """Extract an owner hint from workload annotations or namespace conventions."""
    # Check common ownership annotations
    team = workload.owner_annotations.get("team")
    if not team:
        team = workload.owner_annotations.get("owner.team")
    if not team:
        team = workload.owner_annotations.get("platform.team")

    service = workload.owner_annotations.get("service")
    if not service:
        service = workload.owner_annotations.get("owner.service")

    if team:
        return OwnerRef(team=team, service=service)
    return None


# --- Observation building ---


def _build_evidence_ref(workload: WorkloadMetadata) -> str:
    """Build an opaque evidence reference for a workload."""
    rv = workload.resource_version or "unknown"
    return f"kubernetes://apps/v1/namespaces/{workload.namespace}/{workload.kind.lower()}s/{workload.name}@{rv}"


def _build_observation_id(
    workload: WorkloadMetadata,
    env_var_name: str,
) -> str:
    """Build a deterministic observation ID."""
    container = workload.container_name or "default"
    return f"k8s:{workload.namespace}:{workload.kind.lower()}:{workload.name}:{container}:{env_var_name}"


def _build_consumer_ref(workload: WorkloadMetadata) -> ConsumerRef:
    """Build a ConsumerRef from workload metadata."""
    return ConsumerRef(
        kind=workload.kind,
        namespace=workload.namespace,
        name=workload.name,
        container=workload.container_name,
    )


def _build_secret_authority_ref(
    namespace: str,
    secret_name: Optional[str],
    key: Optional[str] = None,
) -> Optional[str]:
    """Build an opaque secret authority reference."""
    if not secret_name:
        return None
    ref = f"kubernetes-secret:{namespace}/{secret_name}"
    if key:
        ref += f"#{key}"
    return ref


def _classify_risk_signals(
    env_var_name: str,
    has_secret_ref: bool,
    credential_class: Optional[str],
) -> tuple[str, ...]:
    """Classify risk signals for an env var observation."""
    signals: list[str] = []

    if not has_secret_ref:
        # Inline value — this is the highest-risk pattern
        signals.append(RISK_SIGNAL_INLINE_ENV_SECRET)
        signals.append(RISK_SIGNAL_NO_SECRET_REF)
    else:
        signals.append(RISK_SIGNAL_K8S_SECRET_DELIVERY)

    if credential_class == CREDENTIAL_CLASS_POSTGRESQL_LOGIN:
        signals.append(RISK_SIGNAL_RUNTIME_DB_ACCESS)
    elif credential_class == CREDENTIAL_CLASS_OBJECT_STORAGE_KEY:
        signals.append(RISK_SIGNAL_OBJECT_STORAGE_ACCESS)

    return tuple(signals)


# --- Main adapter function ---


def discover_kubernetes_credentials(
    *,
    client: KubernetesDiscoveryClient,
    namespace: str,
    environment: str = "dev",
    observed_at: Optional[str] = None,
) -> tuple[CredentialObservation, ...]:
    """Discover credential references in Kubernetes workload metadata.

    This is the main adapter function. It:
    1. Lists workloads in the namespace via the pluggable client.
    2. Examines env vars, envFrom, and volume secrets for credential references.
    3. Classifies credential class from env var names.
    4. Builds CredentialObservation values with risk signals.
    5. Validates each observation is safe (no secret material).
    6. Returns a tuple of observations.

    The adapter NEVER reads Secret.data. It only reads workload metadata
    to identify credential delivery patterns.

    Args:
        client: Pluggable Kubernetes client (real or synthetic).
        namespace: Kubernetes namespace to scan.
        environment: Environment label for observations (e.g. "dev", "prod").
        observed_at: Optional ISO timestamp; defaults to now.

    Returns:
        Tuple of CredentialObservation values with source="kubernetes".

    Raises:
        UnsafeObservationError: If any observation contains secret material.
    """
    timestamp = observed_at or _utc_now_iso()
    observations: list[CredentialObservation] = []

    workloads = client.list_workloads(namespace)

    for workload in workloads:
        owner_hint = _extract_owner_hint(workload)
        consumer_ref = _build_consumer_ref(workload)
        evidence_ref = _build_evidence_ref(workload)

        # Process env vars
        for env_var in workload.env_vars:
            credential_class = _infer_credential_class(env_var.name)
            if credential_class is None:
                continue  # Not a credential env var

            has_secret_ref = env_var.secret_ref_name is not None
            risk_signals = _classify_risk_signals(
                env_var_name=env_var.name,
                has_secret_ref=has_secret_ref,
                credential_class=credential_class,
            )

            secret_authority = _build_secret_authority_ref(
                namespace=workload.namespace,
                secret_name=env_var.secret_ref_name,
                key=env_var.secret_ref_key,
            )

            # If no secret ref but has inline value, the authority is "inline"
            # (we do NOT include the value)
            if not has_secret_ref:
                secret_authority = f"inline-env:{workload.namespace}/{workload.name}#{env_var.name}"

            obs = CredentialObservation(
                observation_id=_build_observation_id(workload, env_var.name),
                source=COVERAGE_SOURCE_KUBERNETES,
                observed_at=timestamp,
                environment=environment,
                credential_class=credential_class,
                provider_ref=None,  # Kubernetes adapter can't see provider identity
                provider_identity_ref=None,
                secret_authority_ref=secret_authority,
                consumer_refs=(consumer_ref,),
                owner_hint=owner_hint,
                risk_signals=risk_signals,
                exposure_class=None,
                evidence_ref=evidence_ref,
                plaintext_retained=False,
            )
            assert_observation_safe(obs)
            observations.append(obs)

        # Process envFrom blocks — these pull all keys from a Secret
        for env_from in workload.env_from:
            # envFrom pulls all keys; we create one observation per envFrom
            # with credential_class unknown (we can't see individual keys)
            obs = CredentialObservation(
                observation_id=f"k8s:{workload.namespace}:{workload.kind.lower()}:{workload.name}:envfrom:{env_from.secret_ref_name}",
                source=COVERAGE_SOURCE_KUBERNETES,
                observed_at=timestamp,
                environment=environment,
                credential_class=None,  # unknown without seeing keys
                provider_ref=None,
                provider_identity_ref=None,
                secret_authority_ref=_build_secret_authority_ref(
                    namespace=workload.namespace,
                    secret_name=env_from.secret_ref_name,
                ),
                consumer_refs=(consumer_ref,),
                owner_hint=owner_hint,
                risk_signals=(RISK_SIGNAL_K8S_SECRET_DELIVERY,),
                exposure_class=None,
                evidence_ref=evidence_ref,
                plaintext_retained=False,
            )
            assert_observation_safe(obs)
            observations.append(obs)

        # Process volume secrets
        for vol_secret in workload.volume_secrets:
            obs = CredentialObservation(
                observation_id=f"k8s:{workload.namespace}:{workload.kind.lower()}:{workload.name}:volume:{vol_secret.volume_name}",
                source=COVERAGE_SOURCE_KUBERNETES,
                observed_at=timestamp,
                environment=environment,
                credential_class=None,  # unknown without seeing keys
                provider_ref=None,
                provider_identity_ref=None,
                secret_authority_ref=_build_secret_authority_ref(
                    namespace=workload.namespace,
                    secret_name=vol_secret.secret_ref_name,
                ),
                consumer_refs=(consumer_ref,),
                owner_hint=owner_hint,
                risk_signals=(RISK_SIGNAL_K8S_SECRET_DELIVERY,),
                exposure_class=None,
                evidence_ref=evidence_ref,
                plaintext_retained=False,
            )
            assert_observation_safe(obs)
            observations.append(obs)

    return tuple(observations)

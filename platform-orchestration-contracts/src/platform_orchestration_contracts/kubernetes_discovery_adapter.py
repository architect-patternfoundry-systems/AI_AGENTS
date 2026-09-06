"""Kubernetes metadata discovery adapter — Phase 1 read-only.

Discovers credential references in Kubernetes workload metadata without
reading Secret.data. The adapter examines:

- Deployment, StatefulSet, DaemonSet, Job, CronJob env var references
- envFrom secretRef blocks
- volumes.secret references
- ExternalSecret and SecretStore/ClusterSecretStore resources
- ServiceAccount annotations (for workload identity hints)

CRITICAL SECURITY RULE:
    The adapter may detect that a credential-like env var has an inline
    value, but it must never store, return, log, compare, fingerprint,
    or include that value in any output object. The WorkloadEnvVar
    dataclass carries only `inline_value_present: bool`, never the value
    itself. The client implementation is responsible for discarding the
    value immediately when extracting WorkloadEnvVar from API responses.

Required RBAC for the adapter service account:
    get/list/watch:
      deployments, statefulsets, daemonsets, jobs, cronjobs
      configmaps (only if used for secret source references)
      externalsecrets, secretstores, clustersecretstores
      serviceaccounts
    secrets: NOT REQUIRED — do not grant Secret data read

NOTE on inline values: Kubernetes Deployment objects contain pod template
env values in spec.template.spec.containers[].env[].value. A get/list
permission on Deployments gives the client access to those values. The
client implementation MUST reduce inline values to a Boolean presence
signal before constructing WorkloadEnvVar. See ADR-038 for the target
state of eliminating inline secrets entirely.

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


# --- Errors ---


class MalformedWorkloadError(ValueError):
    """Raised when a workload env var has both inline value and secretKeyRef.

    Kubernetes API semantics allow only one of `value` or `valueFrom` per
    env var. If a client reports both inline_value_present=True and a
    secret_ref_name, the workload metadata is malformed and the adapter
    rejects it rather than making an arbitrary classification.
    """

    def __init__(self, workload_ref: str, env_var_name: str):
        self.workload_ref = workload_ref
        self.env_var_name = env_var_name
        super().__init__(
            f"Workload {workload_ref} env var {env_var_name!r} has both "
            f"inline_value_present and secret_ref_name; this is malformed"
        )


# --- Risk signals emitted by the Kubernetes adapter ---

RISK_SIGNAL_K8S_SECRET_DELIVERY = "credential-delivered-through-kubernetes-secret"
RISK_SIGNAL_INLINE_ENV_SECRET = "credential-inlined-in-env-var"
RISK_SIGNAL_RUNTIME_DB_ACCESS = "runtime-database-access"
RISK_SIGNAL_OBJECT_STORAGE_ACCESS = "object-storage-access"
RISK_SIGNAL_EXTERNAL_SECRET_REF = "credential-managed-via-external-secrets"
RISK_SIGNAL_SHARED_SECRET_ACROSS_NAMESPACES = "shared-secret-across-namespaces"
RISK_SIGNAL_NO_SECRET_REF = "credential-env-var-without-secret-reference"

# --- Exposure classes for inline credential detection ---

EXPOSURE_ACTIVE_IN_SOURCE = "active_in_source"
EXPOSURE_SECRET_DELIVERED = "secret_delivered"  # secretKeyRef — not necessarily managed/rotated
EXPOSURE_SECRET_DELIVERED_SHARED = "secret_delivered_shared"  # envFrom — potentially shared across consumers
EXPOSURE_EXTERNAL_SECRET_DELIVERED = "external_secret_delivered"
EXPOSURE_CERTIFICATE_DELIVERED = "certificate_delivered"  # volume-mounted TLS secret
EXPOSURE_UNKNOWN = "unknown"

# Deprecated alias for backward compatibility — prefer EXPOSURE_SECRET_DELIVERED
EXPOSURE_MANAGED_VIA_SECRET_REF = "secret_delivered"

# --- Default action mapping ---

ACTION_EMERGENCY_ROTATION = "emergency_rotation"
ACTION_ENROLLMENT_CANDIDATE = "enrollment_candidate"
ACTION_INVENTORY_ONLY = "inventory_only"
ACTION_CERTIFICATE_LIFECYCLE = "certificate_lifecycle"

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
    """A single env var from a workload, with delivery mode metadata.

    CRITICAL: This dataclass NEVER carries the inline value. The client
    implementation must reduce any inline value to `inline_value_present=True`
    before constructing this object. The actual value must be discarded
    immediately and never assigned to a local variable, log record,
    exception, fingerprint, or returned object.

    A env var is one of:
    - secretKeyRef: secret_ref_name and secret_ref_key are set, inline_value_present is False
    - inline: inline_value_present is True, secret_ref_name is None
    - unresolved: both are False/None (env var exists but source is unclear)
    - MALFORMED: both inline_value_present and secret_ref_name are set → rejected
    """

    name: str
    inline_value_present: bool = False  # True if env.value was present (value itself is discarded)
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

    The client MUST discard any inline env var values before constructing
    WorkloadEnvVar objects. Only `inline_value_present: bool` is retained.
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

    CRITICAL: When extracting env vars from workload manifests, the
    client MUST discard any inline `env.value` immediately and set
    `inline_value_present=True` on the WorkloadEnvVar. The actual value
    must never be stored, logged, or returned in any form.

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
    inline_value_present: bool,
    credential_class: Optional[str],
) -> tuple[str, ...]:
    """Classify risk signals for an env var observation."""
    signals: list[str] = []

    if inline_value_present and not has_secret_ref:
        # Inline value — this is the highest-risk pattern
        signals.append(RISK_SIGNAL_INLINE_ENV_SECRET)
        signals.append(RISK_SIGNAL_NO_SECRET_REF)
    elif has_secret_ref:
        signals.append(RISK_SIGNAL_K8S_SECRET_DELIVERY)
    else:
        # Unresolved — env var exists but no value and no secretRef
        signals.append(RISK_SIGNAL_NO_SECRET_REF)

    if credential_class == CREDENTIAL_CLASS_POSTGRESQL_LOGIN:
        signals.append(RISK_SIGNAL_RUNTIME_DB_ACCESS)
    elif credential_class == CREDENTIAL_CLASS_OBJECT_STORAGE_KEY:
        signals.append(RISK_SIGNAL_OBJECT_STORAGE_ACCESS)

    return tuple(signals)


def _determine_exposure_class(
    inline_value_present: bool,
    has_secret_ref: bool,
) -> str:
    """Determine exposure class from delivery mode."""
    if inline_value_present and not has_secret_ref:
        return EXPOSURE_ACTIVE_IN_SOURCE
    if has_secret_ref:
        return EXPOSURE_SECRET_DELIVERED
    return EXPOSURE_UNKNOWN


def _determine_default_action(
    inline_value_present: bool,
    credential_class: Optional[str],
    has_secret_ref: bool,
) -> str:
    """Determine recommended default action from exposure and credential class."""
    if inline_value_present and not has_secret_ref:
        # Inline credential — emergency rotation required
        return ACTION_EMERGENCY_ROTATION
    if has_secret_ref:
        return ACTION_ENROLLMENT_CANDIDATE
    return ACTION_INVENTORY_ONLY


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
    4. Builds CredentialObservation values with risk signals and exposure class.
    5. Validates each observation is safe (no secret material).
    6. Returns a tuple of observations.

    SECURITY INVARIANT:
        The adapter never receives, stores, logs, or returns inline secret
        values. The WorkloadEnvVar dataclass carries only
        `inline_value_present: bool`. The client implementation is
        responsible for discarding values before constructing WorkloadEnvVar.

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
        MalformedWorkloadError: If an env var has both inline_value_present
            and secret_ref_name (Kubernetes only allows one of value/valueFrom).
    """
    timestamp = observed_at or _utc_now_iso()
    observations: list[CredentialObservation] = []

    workloads = client.list_workloads(namespace)

    for workload in workloads:
        owner_hint = _extract_owner_hint(workload)
        consumer_ref = _build_consumer_ref(workload)
        evidence_ref = _build_evidence_ref(workload)
        workload_ref = f"{workload.namespace}/{workload.kind}:{workload.name}"

        # Process env vars
        for env_var in workload.env_vars:
            credential_class = _infer_credential_class(env_var.name)
            if credential_class is None:
                continue  # Not a credential env var

            # Reject malformed env vars: both inline and secretKeyRef is invalid
            if env_var.inline_value_present and env_var.secret_ref_name:
                raise MalformedWorkloadError(
                    workload_ref=workload_ref,
                    env_var_name=env_var.name,
                )

            has_secret_ref = env_var.secret_ref_name is not None
            risk_signals = _classify_risk_signals(
                env_var_name=env_var.name,
                has_secret_ref=has_secret_ref,
                inline_value_present=env_var.inline_value_present,
                credential_class=credential_class,
            )

            exposure_class = _determine_exposure_class(
                inline_value_present=env_var.inline_value_present,
                has_secret_ref=has_secret_ref,
            )

            default_action = _determine_default_action(
                inline_value_present=env_var.inline_value_present,
                credential_class=credential_class,
                has_secret_ref=has_secret_ref,
            )

            # Build secret authority reference
            if env_var.inline_value_present:
                # Inline — authority is the env var location itself (not the value)
                secret_authority = f"inline-env:{workload.namespace}/{workload.name}#{env_var.name}"
            elif has_secret_ref:
                secret_authority = _build_secret_authority_ref(
                    namespace=workload.namespace,
                    secret_name=env_var.secret_ref_name,
                    key=env_var.secret_ref_key,
                )
            else:
                secret_authority = None

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
                exposure_class=exposure_class,
                evidence_ref=evidence_ref,
                plaintext_retained=False,
                inline_value_present=env_var.inline_value_present,
                default_action=default_action,
            )
            assert_observation_safe(obs)
            observations.append(obs)

        # Process envFrom blocks — these pull all keys from a Secret
        for env_from in workload.env_from:
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
                exposure_class=EXPOSURE_SECRET_DELIVERED_SHARED,
                evidence_ref=evidence_ref,
                plaintext_retained=False,
                inline_value_present=False,
                default_action=ACTION_ENROLLMENT_CANDIDATE,
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
                exposure_class=EXPOSURE_CERTIFICATE_DELIVERED,
                evidence_ref=evidence_ref,
                plaintext_retained=False,
                inline_value_present=False,
                default_action=ACTION_CERTIFICATE_LIFECYCLE,
            )
            assert_observation_safe(obs)
            observations.append(obs)

    return tuple(observations)


# --- Raw API boundary conversion functions ---
#
# These functions convert raw Kubernetes API objects (from the Kubernetes
# Python client library) into the adapter's safe immutable metadata
# dataclasses. They are the CRITICAL BOUNDARY where inline secret values
# are discarded.
#
# SECURITY RULES for boundary conversion:
# 1. Never assign api_env.value to any variable, field, log, or exception.
# 2. Never serialize the raw API object (no repr, to_dict, json.dumps).
# 3. Log only opaque resource coordinates (namespace, kind, name, env_var_name).
# 4. Return only safe immutable dataclasses (WorkloadEnvVar, WorkloadMetadata).
# 5. If the raw object is malformed, raise with opaque identifiers only.


def to_workload_env_var(api_env_var: Any) -> WorkloadEnvVar:
    """Convert a raw Kubernetes API env var to a safe WorkloadEnvVar.

    This is the CRITICAL BOUNDARY where inline secret values are discarded.
    The raw api_env_var.value is checked for presence only, then discarded.
    The actual value must never be assigned to a local variable, log record,
    exception, fingerprint, or returned object.

    Args:
        api_env_var: A raw Kubernetes API env var object with attributes:
            - name: str
            - value: Optional[str] — discarded immediately
            - value_from: Optional[object] with optional secret_key_ref

    Returns:
        WorkloadEnvVar with only safe metadata (no secret values).

    Raises:
        ValueError: If the env var has both value and valueFrom (malformed).
    """
    name = api_env_var.name
    has_inline_value = api_env_var.value is not None

    secret_ref_name = None
    secret_ref_key = None

    value_from = getattr(api_env_var, "value_from", None)
    if value_from is not None:
        secret_key_ref = getattr(value_from, "secret_key_ref", None)
        if secret_key_ref is not None:
            secret_ref_name = getattr(secret_key_ref, "name", None)
            secret_ref_key = getattr(secret_key_ref, "key", None)

    # Kubernetes API semantics: value and valueFrom are mutually exclusive.
    # If both are present, the object is malformed.
    if has_inline_value and secret_ref_name is not None:
        raise ValueError(
            f"Env var {name!r} has both inline value and secretKeyRef; "
            f"this is malformed (Kubernetes API requires mutually exclusive)"
        )

    return WorkloadEnvVar(
        name=name,
        inline_value_present=has_inline_value,
        secret_ref_name=secret_ref_name,
        secret_ref_key=secret_ref_key,
    )


def to_workload_metadata(
    *,
    kind: str,
    namespace: str,
    name: str,
    api_containers: tuple[Any, ...],
    resource_version: Optional[str] = None,
    owner_annotations: Optional[dict[str, str]] = None,
    service_account: Optional[str] = None,
) -> WorkloadMetadata:
    """Convert raw Kubernetes API container specs to safe WorkloadMetadata.

    This function iterates over raw API container objects and extracts
    only safe metadata. Inline env var values are discarded at the
    boundary via to_workload_env_var(). Raw container objects are never
    stored, logged, or serialized.

    Args:
        kind: Workload kind ("Deployment", "StatefulSet", etc.)
        namespace: Kubernetes namespace
        name: Workload name
        api_containers: Tuple of raw API container objects, each with:
            - name: str
            - env: list of raw env var objects
            - env_from: list of raw envFrom objects
            - volume_mounts: list of raw volume mount objects (optional)
        resource_version: Kubernetes resource version
        owner_annotations: Dict of annotation key → value
        service_account: ServiceAccount name

    Returns:
        WorkloadMetadata with only safe metadata (no secret values).
    """
    all_env_vars: list[WorkloadEnvVar] = []
    all_env_from: list[WorkloadEnvFrom] = []
    container_name: Optional[str] = None

    for container in api_containers:
        if container_name is None:
            container_name = getattr(container, "name", None)

        # Convert env vars — values discarded at boundary
        raw_env = getattr(container, "env", None) or []
        for raw_env_var in raw_env:
            safe_env_var = to_workload_env_var(raw_env_var)
            all_env_vars.append(safe_env_var)

        # Convert envFrom — only secret references, no values
        raw_env_from = getattr(container, "env_from", None) or []
        for raw_ef in raw_env_from:
            secret_ref = getattr(raw_ef, "secret_ref", None)
            if secret_ref is not None:
                ref_name = getattr(secret_ref, "name", None)
                if ref_name:
                    all_env_from.append(WorkloadEnvFrom(
                        secret_ref_name=ref_name,
                        optional=getattr(secret_ref, "optional", False) or False,
                    ))

    return WorkloadMetadata(
        kind=kind,
        namespace=namespace,
        name=name,
        container_name=container_name,
        env_vars=tuple(all_env_vars),
        env_from=tuple(all_env_from),
        volume_secrets=(),  # volume secrets extracted separately if needed
        service_account=service_account,
        owner_annotations=owner_annotations or {},
        resource_version=resource_version,
    )


# --- Log scrubber for runtime safeguard ---
#
# A logging filter that redacts known URI/password/token patterns before
# records leave the process. This is a defense-in-depth measure — the
# adapter itself never carries secret values, but the Kubernetes Python
# client library or other dependencies might log raw API responses in
# debug mode. This filter ensures such accidental logs are scrubbed.

import logging
import re as _re

# Patterns that indicate secret-bearing content in log messages.
# Each pattern maps to a replacement string.
_LOG_SCRUB_PATTERNS: tuple[tuple[_re.Pattern, str], ...] = (
    # DSN / connection strings with embedded passwords
    (_re.compile(r"(postgres(?:ql)?://[^:]+:)[^@]+(@)", _re.IGNORECASE), r"\1***REDACTED***\2"),
    (_re.compile(r"(mysql://[^:]+:)[^@]+(@)", _re.IGNORECASE), r"\1***REDACTED***\2"),
    (_re.compile(r"(mongodb(?:\+srv)?://[^:]+:)[^@]+(@)", _re.IGNORECASE), r"\1***REDACTED***\2"),
    (_re.compile(r"(redis://:[^@]+@)", _re.IGNORECASE), "redis://:***REDACTED***@"),
    # password= / passwd= key-value pairs
    (_re.compile(r"(password\s*=\s*)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    (_re.compile(r"(passwd\s*=\s*)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    # token= / api_key= / access_key= / secret_key=
    (_re.compile(r"(token\s*=\s*)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    (_re.compile(r"(api_key\s*=\s*)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    (_re.compile(r"(access_key\s*=\s*)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    (_re.compile(r"(secret_key\s*=\s*)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    (_re.compile(r"(aws_secret_access_key\s*=\s*)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    # Authorization headers
    (_re.compile(r"(authorization\s*:\s*bearer\s+)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    (_re.compile(r"(authorization\s*:\s*basic\s+)\S+", _re.IGNORECASE), r"\1***REDACTED***"),
    # PEM key blocks
    (_re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     "***REDACTED PEM KEY BLOCK***"),
)


class SecretScrubbingFilter(logging.Filter):
    """Logging filter that redacts secret-bearing patterns from log records.

    This is a defense-in-depth measure. The adapter itself never carries
    secret values, but the Kubernetes Python client library or other
    dependencies might log raw API responses in debug mode. This filter
    ensures such accidental logs are scrubbed before they leave the process.

    Install on the root logger or specific loggers:
        filter = SecretScrubbingFilter()
        logging.getLogger("kubernetes").addFilter(filter)
        logging.getLogger("platform_orchestration_contracts").addFilter(filter)
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Scrub secret patterns from the log message and return True."""
        msg = record.getMessage()
        scrubbed = msg
        for pattern, replacement in _LOG_SCRUB_PATTERNS:
            scrubbed = pattern.sub(replacement, scrubbed)
        if scrubbed != msg:
            # Replace the message in-place
            record.msg = scrubbed
            record.args = None
        return True


def install_secret_scrubbing_filter(logger_name: str = "") -> SecretScrubbingFilter:
    """Install SecretScrubbingFilter on the named logger (or root if empty).

    Returns the filter so callers can remove it later if needed.
    """
    logger = logging.getLogger(logger_name)
    # Avoid duplicate filters
    for existing in logger.filters:
        if isinstance(existing, SecretScrubbingFilter):
            return existing
    filt = SecretScrubbingFilter()
    logger.addFilter(filt)
    return filt


# --- Real Kubernetes Python client implementation ---
#
# This client uses the Kubernetes Python client library to list workloads
# in a single namespace. It is deliberately boring, narrow, and non-reusable
# outside discovery.
#
# SECURITY PROPERTIES:
# 1. Namespace is configured at construction and checked at runtime.
# 2. Returns only WorkloadMetadata, never raw client objects.
# 3. Failures log resource type/name/namespace — never response bodies.
# 4. No method exists for read_namespaced_secret.
# 5. No generic "dump resource" helper exists.
# 6. No debug switch ever serializes raw Kubernetes objects.
# 7. Raw API exceptions are NOT chained (no `raise ... from raw_exception`).
# 8. The kubernetes library is imported lazily so the contract package
#    does not require it as a dependency.


class KubernetesPythonDiscoveryClient:
    """Real Kubernetes discovery client using the Python client library.

    This client is namespace-scoped: it can only list workloads in the
    namespace specified at construction time. It never reads Secret.data
    and has no method for reading Secret objects.

    The client uses to_workload_metadata() at the API boundary to convert
    raw Kubernetes API objects into safe immutable metadata dataclasses.
    Inline env var values are discarded at that boundary.

    RBAC requirements for the service account:
        get/list/watch:
          apps/deployments, apps/statefulsets, apps/daemonsets
          batch/jobs, batch/cronjobs
          externalsecrets (if external-secrets.io is installed)
        NOT granted:
          core/secrets (Secret data reads are prohibited)

    Args:
        namespace: Kubernetes namespace to scan (e.g. "cts").
        apps_api: Optional pre-configured AppsV1Api instance.
        batch_api: Optional pre-configured BatchV1Api instance.
        load_config: If True, call kubernetes.config.load_kube_config()
            during construction. Set to False in tests when providing
            mock APIs.
    """

    def __init__(
        self,
        namespace: str,
        apps_api: Any = None,
        batch_api: Any = None,
        load_config: bool = True,
    ):
        self._namespace = namespace
        self._apps_api = apps_api
        self._batch_api = batch_api

        if load_config:
            self._load_kubernetes_config()

        # Install log scrubbing on the kubernetes client logger
        # to prevent accidental secret leakage in debug logs
        install_secret_scrubbing_filter("kubernetes")
        install_secret_scrubbing_filter("urllib3")

    def _load_kubernetes_config(self) -> None:
        """Load Kubernetes configuration using lazy import."""
        try:
            from kubernetes import config as k8s_config
        except ImportError as e:
            raise ImportError(
                "kubernetes package is required for KubernetesPythonDiscoveryClient. "
                "Install with: pip install kubernetes"
            ) from None  # Do NOT chain the original ImportError

        try:
            k8s_config.load_incluster_config()
        except Exception:
            # Fall back to kubeconfig for local/development use
            k8s_config.load_kube_config()

    def _ensure_apis(self) -> None:
        """Lazily initialize API clients if not provided."""
        if self._apps_api is not None and self._batch_api is not None:
            return
        try:
            from kubernetes.client import AppsV1Api, BatchV1Api
        except ImportError as e:
            raise ImportError(
                "kubernetes package is required for KubernetesPythonDiscoveryClient. "
                "Install with: pip install kubernetes"
            ) from None  # Do NOT chain

        if self._apps_api is None:
            self._apps_api = AppsV1Api()
        if self._batch_api is None:
            self._batch_api = BatchV1Api()

    def list_workloads(self, namespace: str) -> tuple[WorkloadMetadata, ...]:
        """List workload metadata in the specified namespace.

        Args:
            namespace: Kubernetes namespace to scan. Must match the
                namespace configured at construction time.

        Returns:
            Tuple of WorkloadMetadata values with only safe metadata.

        Raises:
            ValueError: If namespace doesn't match the configured scope.
            DiscoveryError: If the Kubernetes API call fails. The error
                message contains only opaque resource coordinates, never
                response bodies or raw API objects.
        """
        if namespace != self._namespace:
            raise ValueError(
                f"Discovery client is namespace-scoped to {self._namespace!r}; "
                f"cannot list workloads in {namespace!r}"
            )

        self._ensure_apis()
        results: list[WorkloadMetadata] = []

        # Deployments
        try:
            deployments = self._apps_api.list_namespaced_deployment(namespace=namespace)
            for item in (deployments.items if deployments else []):
                results.append(self._convert_workload(item, "Deployment", namespace))
        except Exception as e:
            raise DiscoveryError(
                f"Failed to list Deployments in namespace {namespace!r}",
                resource_kind="Deployment",
                namespace=namespace,
            ) from None  # Do NOT chain raw exception

        # StatefulSets
        try:
            statefulsets = self._apps_api.list_namespaced_stateful_set(namespace=namespace)
            for item in (statefulsets.items if statefulsets else []):
                results.append(self._convert_workload(item, "StatefulSet", namespace))
        except Exception:
            raise DiscoveryError(
                f"Failed to list StatefulSets in namespace {namespace!r}",
                resource_kind="StatefulSet",
                namespace=namespace,
            ) from None

        # DaemonSets
        try:
            daemonsets = self._apps_api.list_namespaced_daemon_set(namespace=namespace)
            for item in (daemonsets.items if daemonsets else []):
                results.append(self._convert_workload(item, "DaemonSet", namespace))
        except Exception:
            raise DiscoveryError(
                f"Failed to list DaemonSets in namespace {namespace!r}",
                resource_kind="DaemonSet",
                namespace=namespace,
            ) from None

        # Jobs
        try:
            jobs = self._batch_api.list_namespaced_job(namespace=namespace)
            for item in (jobs.items if jobs else []):
                results.append(self._convert_workload(item, "Job", namespace))
        except Exception:
            raise DiscoveryError(
                f"Failed to list Jobs in namespace {namespace!r}",
                resource_kind="Job",
                namespace=namespace,
            ) from None

        # CronJobs
        try:
            cronjobs = self._batch_api.list_namespaced_cron_job(namespace=namespace)
            for item in (cronjobs.items if cronjobs else []):
                results.append(self._convert_workload(item, "CronJob", namespace))
        except Exception:
            raise DiscoveryError(
                f"Failed to list CronJobs in namespace {namespace!r}",
                resource_kind="CronJob",
                namespace=namespace,
            ) from None

        return tuple(results)

    def list_external_secrets(self, namespace: str) -> tuple[ExternalSecretMetadata, ...]:
        """List ExternalSecret metadata in the specified namespace.

        This is a stub — ExternalSecret support requires the
        external-secrets.io CRD client, which is not yet implemented.
        Returns an empty tuple for now.
        """
        if namespace != self._namespace:
            raise ValueError(
                f"Discovery client is namespace-scoped to {self._namespace!r}; "
                f"cannot list external secrets in {namespace!r}"
            )
        return ()

    def _convert_workload(
        self,
        api_workload: Any,
        kind: str,
        namespace: str,
    ) -> WorkloadMetadata:
        """Convert a raw Kubernetes API workload object to safe WorkloadMetadata.

        This method extracts only safe metadata from the raw API object.
        Inline env var values are discarded at the boundary via
        to_workload_env_var(). Raw API objects are never stored, logged,
        or serialized.

        Args:
            api_workload: Raw Kubernetes API object (V1Deployment, etc.)
            kind: Workload kind string ("Deployment", "StatefulSet", etc.)
            namespace: Kubernetes namespace

        Returns:
            WorkloadMetadata with only safe metadata (no secret values).
        """
        # Extract metadata using getattr for duck-typing compatibility
        meta = getattr(api_workload, "metadata", None)
        name = getattr(meta, "name", "unknown") if meta else "unknown"
        resource_version = getattr(meta, "resource_version", None) if meta else None
        annotations = dict(getattr(meta, "annotations", None) or {}) if meta else {}

        # Extract pod template containers
        # For Deployment/StatefulSet/DaemonSet: spec.template.spec.containers
        # For Job: spec.template.spec.containers
        # For CronJob: spec.job_template.spec.template.spec.containers
        spec = getattr(api_workload, "spec", None)
        template = getattr(spec, "template", None) if spec else None

        # Handle CronJob's nested job_template
        if template is None and spec is not None:
            job_template = getattr(spec, "job_template", None)
            if job_template is not None:
                template = getattr(job_template, "spec", None)
                if template is not None:
                    template = getattr(template, "template", None)

        template_spec = getattr(template, "spec", None) if template else None
        containers = getattr(template_spec, "containers", None) or () if template_spec else ()
        init_containers = getattr(template_spec, "init_containers", None) or () if template_spec else ()
        all_containers = tuple(containers) + tuple(init_containers)

        # Extract service account
        service_account = getattr(template_spec, "service_account_name", None) if template_spec else None

        # Extract volume secrets
        volume_secrets = self._extract_volume_secrets(template_spec, namespace)

        # Convert containers to safe metadata
        all_env_vars: list[WorkloadEnvVar] = []
        all_env_from: list[WorkloadEnvFrom] = []
        container_name: Optional[str] = None

        for container in all_containers:
            if container_name is None:
                container_name = getattr(container, "name", None)

            raw_env = getattr(container, "env", None) or []
            for raw_env_var in raw_env:
                safe_env_var = to_workload_env_var(raw_env_var)
                all_env_vars.append(safe_env_var)

            raw_env_from = getattr(container, "env_from", None) or []
            for raw_ef in raw_env_from:
                secret_ref = getattr(raw_ef, "secret_ref", None)
                if secret_ref is not None:
                    ref_name = getattr(secret_ref, "name", None)
                    if ref_name:
                        all_env_from.append(WorkloadEnvFrom(
                            secret_ref_name=ref_name,
                            optional=getattr(secret_ref, "optional", False) or False,
                        ))

        return WorkloadMetadata(
            kind=kind,
            namespace=namespace,
            name=name,
            container_name=container_name,
            env_vars=tuple(all_env_vars),
            env_from=tuple(all_env_from),
            volume_secrets=tuple(volume_secrets),
            service_account=service_account,
            owner_annotations=annotations,
            resource_version=resource_version,
        )

    def _extract_volume_secrets(
        self,
        template_spec: Any,
        namespace: str,
    ) -> list[WorkloadVolumeSecret]:
        """Extract volume-mounted Secret references from pod template spec.

        Only extracts the Secret name and volume name — never the data.
        """
        if template_spec is None:
            return []

        volumes = getattr(template_spec, "volumes", None) or []
        result: list[WorkloadVolumeSecret] = []

        for vol in volumes:
            secret_vol = getattr(vol, "secret", None)
            if secret_vol is not None:
                secret_name = getattr(secret_vol, "secret_name", None)
                vol_name = getattr(vol, "name", "unknown")
                if secret_name:
                    result.append(WorkloadVolumeSecret(
                        volume_name=vol_name,
                        secret_ref_name=secret_name,
                    ))

        return result


class DiscoveryError(RuntimeError):
    """Error raised by KubernetesPythonDiscoveryClient on API failures.

    The error message contains only opaque resource coordinates
    (namespace, kind), never response bodies or raw API objects.
    Raw exceptions are NOT chained to prevent leaking response content.
    """

    def __init__(
        self,
        message: str,
        resource_kind: str = "",
        namespace: str = "",
    ):
        self.resource_kind = resource_kind
        self.namespace = namespace
        super().__init__(message)

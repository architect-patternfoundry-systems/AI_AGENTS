"""Credential Discovery Workflow v1 — read-only inventory pipeline.

Implements Phase 1 of ADR-038: an inventory-only controller that discovers
credentials from multiple sources, correlates findings, evaluates rotation
eligibility, and produces redacted posture reports.

This workflow is strictly read-only:
- Reads Kubernetes metadata, not Secret data.
- Reads ExternalSecret/SecretStore and workload resource metadata.
- Reads PostgreSQL role metadata only.
- Reads MinIO identity/policy metadata only.
- Reads already-redacted Gitleaks/CI findings.
- Writes only inventory/evidence metadata.
- Never modifies providers, secret stores, workloads, or rotation schedules.

The workflow is structured as a deterministic pipeline that can be driven
by a Temporal workflow or run standalone for testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .credential_inventory import (
    CredentialSetRecord,
    DiscoveryFinding,
    RotationEligibility,
    evaluate_rotation_eligibility,
    RotationSubject,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
    RISK_CRITICAL,
    ALL_RISK_TIERS,
    LIFECYCLE_DISCOVERED,
    LIFECYCLE_BOOTSTRAP_REQUIRED,
    LIFECYCLE_ENROLLED,
    LIFECYCLE_ROTATION_READY,
    LIFECYCLE_AUTOMATICALLY_MANAGED,
    SOURCE_KUBERNETES,
    SOURCE_GIT,
    SOURCE_GITLEAKS,
    SOURCE_PROVIDER,
    SOURCE_RUNTIME,
    SOURCE_TELEMETRY,
    ConsumerRef,
    OwnerRef,
    AuthorityRef,
    RiskAssessment,
    RotationCapabilities,
)
from .credential_rotation import (
    CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    CREDENTIAL_CLASS_OBJECT_STORAGE_KEY,
    CREDENTIAL_CLASS_API_KEY,
)


# --- Posture report types ---


@dataclass(frozen=True)
class CredentialPostureEntry:
    """A single credential's posture in the discovery report.

    Contains only redacted metadata — no secret values, raw DSNs, or
    unredacted URLs. This is the output unit of the Phase 1 controller.
    """

    credential_set_id: str
    credential_class: str
    environment: str
    owner: Optional[str]  # owner reference, None if unowned
    lifecycle_state: str
    consumer_count: int
    provider_identity_ref: Optional[str]  # opaque reference
    secret_authority_status: Optional[str]  # "managed", "unmanaged", "unknown"
    risk_tier: str
    provider_ready: bool
    execution_ready: bool
    eligible: bool
    blockers: tuple[str, ...]
    exposure_status: str
    last_observed_use: Optional[str]
    enrollment_deadline: Optional[str]
    recommended_next_action: str
    input_fingerprint: str  # from RotationEligibility

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_set_id": self.credential_set_id,
            "credential_class": self.credential_class,
            "environment": self.environment,
            "owner": self.owner,
            "lifecycle_state": self.lifecycle_state,
            "consumer_count": self.consumer_count,
            "provider_identity_ref": self.provider_identity_ref,
            "secret_authority_status": self.secret_authority_status,
            "risk_tier": self.risk_tier,
            "provider_ready": self.provider_ready,
            "execution_ready": self.execution_ready,
            "eligible": self.eligible,
            "blockers": list(self.blockers),
            "exposure_status": self.exposure_status,
            "last_observed_use": self.last_observed_use,
            "enrollment_deadline": self.enrollment_deadline,
            "recommended_next_action": self.recommended_next_action,
            "input_fingerprint": self.input_fingerprint,
        }


@dataclass(frozen=True)
class PostureReport:
    """Aggregated credential posture report from a discovery run.

    This is the primary output of the Phase 1 inventory-only controller.
    It contains redacted metadata only and is safe to persist as evidence
    or display on a security dashboard.
    """

    run_id: str
    evaluated_at: str  # ISO timestamp
    policy_version: str
    total_credentials: int
    eligible_count: int
    blocked_count: int
    unowned_count: int
    orphaned_count: int
    entries: tuple[CredentialPostureEntry, ...]
    summary_by_risk_tier: dict[str, int] = field(default_factory=dict)
    summary_by_lifecycle_state: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "evaluated_at": self.evaluated_at,
            "policy_version": self.policy_version,
            "total_credentials": self.total_credentials,
            "eligible_count": self.eligible_count,
            "blocked_count": self.blocked_count,
            "unowned_count": self.unowned_count,
            "orphaned_count": self.orphaned_count,
            "summary_by_risk_tier": dict(self.summary_by_risk_tier),
            "summary_by_lifecycle_state": dict(self.summary_by_lifecycle_state),
            "entries": [e.to_dict() for e in self.entries],
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    def to_markdown(self) -> str:
        """Render a human-readable Markdown posture report."""
        lines = [
            f"# Credential Posture Report",
            f"",
            f"- **Run ID**: `{self.run_id}`",
            f"- **Evaluated at**: {self.evaluated_at}",
            f"- **Policy version**: {self.policy_version}",
            f"- **Total credentials**: {self.total_credentials}",
            f"- **Eligible for rotation**: {self.eligible_count}",
            f"- **Blocked**: {self.blocked_count}",
            f"- **Unowned**: {self.unowned_count}",
            f"- **Orphaned**: {self.orphaned_count}",
            f"",
            f"## Summary by risk tier",
            f"",
            f"| Risk tier | Count |",
            f"|---|---|",
        ]
        for tier in ALL_RISK_TIERS:
            count = self.summary_by_risk_tier.get(tier, 0)
            if count > 0:
                lines.append(f"| {tier} | {count} |")
        lines.extend([
            f"",
            f"## Summary by lifecycle state",
            f"",
            f"| Lifecycle state | Count |",
            f"|---|---|",
        ])
        for state, count in sorted(self.summary_by_lifecycle_state.items()):
            if count > 0:
                lines.append(f"| {state} | {count} |")
        lines.extend([
            f"",
            f"## Credential details",
            f"",
            f"| Credential set | Class | Risk | Eligible | Blockers | Next action |",
            f"|---|---|---|---|---|---|",
        ])
        for entry in self.entries:
            blockers_str = ", ".join(entry.blockers) if entry.blockers else "—"
            eligible_str = "yes" if entry.eligible else "no"
            lines.append(
                f"| `{entry.credential_set_id}` | {entry.credential_class} "
                f"| {entry.risk_tier} | {eligible_str} "
                f"| {blockers_str} | {entry.recommended_next_action} |"
            )
        return "\n".join(lines)


# --- Discovery pipeline ---


def _recommend_next_action(
    lifecycle_state: str,
    eligible: bool,
    is_unowned: bool,
    is_orphaned: bool,
    blockers: tuple[str, ...],
) -> str:
    """Determine the recommended next action for a credential."""
    if is_unowned:
        return "assign_owner"
    if is_orphaned:
        return "triage_orphaned_credential"
    if lifecycle_state == LIFECYCLE_DISCOVERED:
        return "begin_enrollment"
    if lifecycle_state == LIFECYCLE_BOOTSTRAP_REQUIRED:
        return "complete_bootstrap"
    if eligible and lifecycle_state == LIFECYCLE_ROTATION_READY:
        return "schedule_rotation"
    if not eligible and blockers:
        return f"resolve_blockers: {','.join(blockers[:3])}"
    if lifecycle_state == LIFECYCLE_AUTOMATICALLY_MANAGED:
        return "monitor"
    return "review"


def _summarize_by_risk_tier(
    entries: tuple[CredentialPostureEntry, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.risk_tier] = counts.get(entry.risk_tier, 0) + 1
    return counts


def _summarize_by_lifecycle_state(
    entries: tuple[CredentialPostureEntry, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.lifecycle_state] = counts.get(entry.lifecycle_state, 0) + 1
    return counts


def build_posture_entry(
    record: CredentialSetRecord,
    eligibility: RotationEligibility,
    exposure_status: str = "unknown",
    last_observed_use: Optional[str] = None,
) -> CredentialPostureEntry:
    """Build a posture entry from an inventory record and eligibility decision.

    This is the unit function for the posture pipeline. It combines
    the canonical eligibility evaluation with inventory metadata to
    produce a redacted, dashboard-ready entry.
    """
    owner_ref = None
    if record.owner is not None:
        owner_ref = record.owner.team
        if record.owner.service:
            owner_ref = f"{owner_ref}:{record.owner.service}"

    secret_authority_status = "unknown"
    provider_identity_ref = None
    if record.authority is not None:
        provider_identity_ref = f"{record.authority.provider}"
        if record.authority.namespace and record.authority.secret_name:
            provider_identity_ref += f":{record.authority.namespace}/{record.authority.secret_name}"
        # If it's external secrets or vault, it's managed; kubernetes_secret may be unmanaged
        if record.authority.provider in ("vault", "external_secrets", "aws_secrets_manager"):
            secret_authority_status = "managed"
        elif record.authority.provider == "kubernetes_secret":
            secret_authority_status = "unmanaged"
        else:
            secret_authority_status = "unknown"

    recommended = _recommend_next_action(
        lifecycle_state=record.lifecycle_state,
        eligible=eligibility.eligible,
        is_unowned=record.is_unowned,
        is_orphaned=record.is_orphaned,
        blockers=eligibility.all_blockers,
    )

    return CredentialPostureEntry(
        credential_set_id=record.credential_set_id,
        credential_class=record.credential_class,
        environment=record.environment,
        owner=owner_ref,
        lifecycle_state=record.lifecycle_state,
        consumer_count=len(record.consumers),
        provider_identity_ref=provider_identity_ref,
        secret_authority_status=secret_authority_status,
        risk_tier=eligibility.risk_tier,
        provider_ready=eligibility.provider_ready,
        execution_ready=eligibility.execution_ready,
        eligible=eligibility.eligible,
        blockers=eligibility.all_blockers,
        exposure_status=exposure_status,
        last_observed_use=last_observed_use,
        enrollment_deadline=record.enrollment_deadline,
        recommended_next_action=recommended,
        input_fingerprint=eligibility.input_fingerprint,
    )


def evaluate_posture(
    *,
    run_id: str,
    records: tuple[CredentialSetRecord, ...],
    risk_tier_overrides: Optional[dict[str, str]] = None,
    capability_overrides: Optional[dict[str, RotationCapabilities]] = None,
    policy_version: str = "1",
) -> PostureReport:
    """Evaluate posture for a set of credential inventory records.

    This is the main Phase 1 pipeline function. It:
    1. Evaluates rotation eligibility for each credential using the
       canonical evaluator.
    2. Builds a posture entry for each credential.
    3. Aggregates into a PostureReport with summaries.

    The function is read-only and produces only redacted metadata.
    No provider mutation, secret reads, or workload changes occur.

    Args:
        run_id: Unique identifier for this discovery run.
        records: Credential inventory records to evaluate.
        risk_tier_overrides: Optional map of credential_set_id → risk_tier.
            If not provided, the record's risk tier is used.
        capability_overrides: Optional map of credential_set_id → capabilities.
            If not provided, the record's capabilities are used.
        policy_version: Policy version for eligibility evaluation.

    Returns:
        PostureReport with entries for each credential.
    """
    from datetime import datetime, timezone

    entries: list[CredentialPostureEntry] = []

    for record in records:
        risk_tier = record.risk.tier
        if risk_tier_overrides and record.credential_set_id in risk_tier_overrides:
            risk_tier = risk_tier_overrides[record.credential_set_id]

        caps = record.capabilities
        if capability_overrides and record.credential_set_id in capability_overrides:
            caps = capability_overrides[record.credential_set_id]

        provider_ref = "unknown:unknown"
        if record.authority is not None:
            provider_ref = record.authority.provider
            if record.authority.namespace and record.authority.secret_name:
                provider_ref += f":{record.authority.namespace}/{record.authority.secret_name}"

        subject = RotationSubject(
            credential_set_id=record.credential_set_id,
            provider_ref=provider_ref,
            provider_identity_ref=provider_ref,
            secret_authority_ref=provider_ref,
            consumer_set_ref=",".join(f"{c.namespace}/{c.name}" for c in record.consumers) if record.consumers else "none",
            consumer_set_version="discovery:v1",
            rotation_strategy=record.target_strategy or "unknown",
            reload_strategy="unknown",
        )

        eligibility = evaluate_rotation_eligibility(
            subject=subject,
            risk_tier=risk_tier,
            capabilities=caps,
            policy_version=policy_version,
        )

        entry = build_posture_entry(
            record=record,
            eligibility=eligibility,
            exposure_status="unknown",
        )
        entries.append(entry)

    entries_tuple = tuple(entries)
    eligible_count = sum(1 for e in entries if e.eligible)
    blocked_count = sum(1 for e in entries if not e.eligible)
    unowned_count = sum(1 for e in entries if e.owner is None)
    orphaned_count = sum(1 for e in entries if e.consumer_count == 0 and e.lifecycle_state != LIFECYCLE_DISCOVERED)

    return PostureReport(
        run_id=run_id,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        policy_version=policy_version,
        total_credentials=len(entries),
        eligible_count=eligible_count,
        blocked_count=blocked_count,
        unowned_count=unowned_count,
        orphaned_count=orphaned_count,
        entries=entries_tuple,
        summary_by_risk_tier=_summarize_by_risk_tier(entries_tuple),
        summary_by_lifecycle_state=_summarize_by_lifecycle_state(entries_tuple),
    )

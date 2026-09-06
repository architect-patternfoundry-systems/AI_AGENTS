"""One-shot credential discovery runner for Phase 1 CTS namespace scan.

This module provides a CLI entry point for running a single discovery
scan against a Kubernetes namespace. It is designed to be run as a
short-lived Kubernetes Job with tightly scoped RBAC.

Usage:
    python -m platform_orchestration_contracts.run_discovery \\
        --namespace=cts \\
        --sources=kubernetes \\
        --output=/evidence/credential-posture.json

SECURITY PROPERTIES:
1. Reads only workload metadata — never Secret.data
2. Logs only opaque resource coordinates — never raw API objects
3. Output is validated with assert_observation_safe() before persistence
4. Coverage is reported honestly (missing adapters → not_configured)
5. Inline credential signals are flagged as emergency_rotation
6. No Kubernetes mutations are performed
7. No database, MinIO, or provider credentials are required

The runner produces:
- JSON posture report (machine-readable)
- Markdown posture report (human-readable)
- Console summary with emergency remediation items

Exit codes:
    0 — discovery completed successfully
    1 — discovery failed (API error, validation error)
    2 — emergency remediation items found (scan succeeded but found active exposures)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import __version__ as PACKAGE_VERSION
from .credential_discovery_workflow import (
    CredentialObservation,
    COVERAGE_COMPLETED,
    COVERAGE_NOT_CONFIGURED,
    COVERAGE_SOURCE_KUBERNETES,
    COVERAGE_SOURCE_POSTGRES,
    COVERAGE_SOURCE_MINIO,
    COVERAGE_SOURCE_GIT_FINDINGS,
    evaluate_posture,
)
from .credential_inventory import (
    AuthorityRef,
    ConsumerRef,
    CredentialSetRecord,
    LIFECYCLE_DISCOVERED,
    LIFECYCLE_BOOTSTRAP_REQUIRED,
    OwnerRef,
    RISK_HIGH,
    RISK_CRITICAL,
    RISK_LOW,
    RiskAssessment,
    RotationCapabilities,
)
from .kubernetes_discovery_adapter import (
    ACTION_EMERGENCY_ROTATION,
    DiscoveryError,
    EXPOSURE_ACTIVE_IN_SOURCE,
    KubernetesPythonDiscoveryClient,
    discover_kubernetes_credentials,
    install_secret_scrubbing_filter,
)
from .observation_safety import (
    UnsafeObservationError,
    assert_observations_safe,
)

logger = logging.getLogger("platform_orchestration_contracts.run_discovery")


def _setup_logging(level: str = "WARNING") -> None:
    """Configure logging with secret scrubbing filter.

    Kubernetes client and urllib3 debug logs are suppressed to prevent
    accidental raw API response logging. The secret scrubbing filter
    is installed as a final defensive layer.
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    # Suppress Kubernetes client and urllib3 debug logs
    logging.getLogger("kubernetes").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Install secret scrubbing as defense-in-depth
    install_secret_scrubbing_filter("kubernetes")
    install_secret_scrubbing_filter("urllib3")
    install_secret_scrubbing_filter("platform_orchestration_contracts")


def _observation_to_record(obs: CredentialObservation) -> CredentialSetRecord:
    """Convert a CredentialObservation to a CredentialSetRecord for posture evaluation.

    This is a simplified correlation step. In the full pipeline, a
    correlation service would group observations by credential identity.
    For the one-shot scan, each observation becomes a provisional record.
    """
    # Determine lifecycle state from exposure class
    if obs.exposure_class == EXPOSURE_ACTIVE_IN_SOURCE:
        lifecycle_state = LIFECYCLE_BOOTSTRAP_REQUIRED
        risk_tier = RISK_HIGH
    else:
        lifecycle_state = LIFECYCLE_DISCOVERED
        risk_tier = RISK_LOW

    # Build authority reference from secret_authority_ref
    authority = None
    if obs.secret_authority_ref:
        if obs.secret_authority_ref.startswith("kubernetes-secret:"):
            parts = obs.secret_authority_ref.removeprefix("kubernetes-secret:")
            if "#" in parts:
                ns_secret, key = parts.split("#", 1)
            else:
                ns_secret, key = parts, None
            if "/" in ns_secret:
                ns, secret_name = ns_secret.split("/", 1)
            else:
                ns, secret_name = None, ns_secret
            authority = AuthorityRef(
                provider="kubernetes_secret",
                namespace=ns,
                secret_name=secret_name,
                key_names=(key,) if key else (),
            )
        elif obs.secret_authority_ref.startswith("inline-env:"):
            parts = obs.secret_authority_ref.removeprefix("inline-env:")
            if "#" in parts:
                ns_name, env_var = parts.split("#", 1)
            else:
                ns_name, env_var = parts, None
            if "/" in ns_name:
                ns, name = ns_name.split("/", 1)
            else:
                ns, name = None, ns_name
            authority = AuthorityRef(
                provider="inline_env",
                namespace=ns,
                secret_name=name,
            )

    # Build display name from observation context
    display_name = obs.credential_class or "unknown_credential"
    if obs.consumer_refs:
        consumer = obs.consumer_refs[0]
        display_name = f"{consumer.namespace}/{consumer.name}:{display_name}"

    # Sanitize observation_id for use as credential_set_id
    # (credential_set_id must match [a-z0-9][a-z0-9_-]*)
    safe_id = obs.observation_id.lower().replace(":", "-").replace("/", "-").replace("#", "-")

    return CredentialSetRecord(
        credential_set_id=safe_id,
        display_name=display_name,
        credential_class=obs.credential_class or "unknown",
        environment=obs.environment,
        lifecycle_state=lifecycle_state,
        owner=obs.owner_hint,
        authority=authority,
        consumers=obs.consumer_refs,
        risk=RiskAssessment(tier=risk_tier),
        capabilities=RotationCapabilities(),
        target_strategy=obs.default_action,
        current_mode="static_unmanaged" if obs.exposure_class == EXPOSURE_ACTIVE_IN_SOURCE else "unknown",
        target_mode="automatically_managed",
        evidence_refs=(obs.evidence_ref,) if obs.evidence_ref else (),
    )


def _build_coverage(sources: list[str]) -> dict[str, str]:
    """Build coverage map from the --sources argument.

    Sources not listed are marked as not_configured to prevent
    false security assurance from missing adapters.
    """
    coverage = {}
    for source in (COVERAGE_SOURCE_KUBERNETES, COVERAGE_SOURCE_POSTGRES,
                   COVERAGE_SOURCE_MINIO, COVERAGE_SOURCE_GIT_FINDINGS):
        if source in sources:
            coverage[source] = COVERAGE_COMPLETED
        else:
            coverage[source] = COVERAGE_NOT_CONFIGURED
    return coverage


def _count_emergency_items(observations: tuple[CredentialObservation, ...]) -> int:
    """Count observations requiring emergency rotation."""
    return sum(
        1 for o in observations
        if o.default_action == ACTION_EMERGENCY_ROTATION
        or o.exposure_class == EXPOSURE_ACTIVE_IN_SOURCE
    )


def _format_emergency_items(observations: tuple[CredentialObservation, ...]) -> list[str]:
    """Format emergency remediation items for console output.

    Contains only workload identity and variable name — never values.
    """
    items = []
    for obs in observations:
        if obs.default_action == ACTION_EMERGENCY_ROTATION:
            consumer = obs.consumer_refs[0] if obs.consumer_refs else None
            if consumer:
                location = f"{consumer.kind} {consumer.namespace}/{consumer.name}"
                if consumer.container:
                    location += f" container={consumer.container}"
                # Extract env var name from observation_id (last segment)
                env_var = obs.observation_id.rsplit(":", 1)[-1]
                items.append(
                    f"  EMERGENCY: {location} env_var={env_var} "
                    f"class={obs.credential_class} action={obs.default_action}"
                )
            else:
                items.append(
                    f"  EMERGENCY: {obs.observation_id} "
                    f"class={obs.credential_class} action={obs.default_action}"
                )
    return items


def run_discovery(
    *,
    namespace: str,
    sources: list[str],
    output_path: Optional[str] = None,
    environment: str = "dev",
    run_id: Optional[str] = None,
    log_level: str = "WARNING",
) -> int:
    """Run a one-shot credential discovery scan.

    Args:
        namespace: Kubernetes namespace to scan (e.g. "cts").
        sources: List of discovery sources to enable (e.g. ["kubernetes"]).
        output_path: Path to write JSON posture report. If None, print to stdout.
        environment: Environment label for observations.
        run_id: Unique run identifier. If None, generated from timestamp.
        log_level: Logging level (WARNING, INFO, DEBUG).

    Returns:
        Exit code: 0=success, 1=error, 2=emergency items found.
    """
    _setup_logging(log_level)

    if run_id is None:
        run_id = f"discovery-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    logger.info(
        "Starting credential discovery",
        extra={"namespace": namespace, "sources": sources, "run_id": run_id},
    )

    # Only Kubernetes is implemented in Phase 1
    if "kubernetes" not in sources:
        logger.error("Only kubernetes source is implemented in Phase 1")
        return 1

    # Run Kubernetes discovery
    try:
        client = KubernetesPythonDiscoveryClient(namespace=namespace)
        observations = discover_kubernetes_credentials(
            client=client,
            namespace=namespace,
            environment=environment,
        )
    except DiscoveryError as e:
        logger.error(
            "Kubernetes discovery failed",
            extra={"namespace": namespace, "resource_kind": e.resource_kind},
        )
        return 1
    except ValueError as e:
        logger.error(
            "Discovery configuration error",
            extra={"error_type": type(e).__name__},
        )
        return 1

    # Validate all observations are safe
    try:
        assert_observations_safe(observations)
    except UnsafeObservationError as e:
        logger.error(
            "Unsafe observation detected — aborting",
            extra={"observation_id": e.observation_id},
        )
        return 1

    logger.info(
        "Discovery completed",
        extra={
            "namespace": namespace,
            "observations": len(observations),
            "emergency_items": _count_emergency_items(observations),
        },
    )

    # Convert observations to inventory records
    records = tuple(_observation_to_record(o) for o in observations)

    # Build coverage map
    coverage = _build_coverage(sources)

    # Evaluate posture
    evidence_ref = f"security-evidence://discovery/{namespace}/{run_id}"
    report = evaluate_posture(
        run_id=run_id,
        records=records,
        policy_version="1",
        coverage=coverage,
        evidence_manifest_ref=evidence_ref,
    )

    # Write JSON report
    report_json = report.to_json()
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(report_json, encoding="utf-8")
        logger.info(
            "JSON report written",
            extra={"path": str(output_file), "bytes": len(report_json)},
        )

        # Also write Markdown report alongside
        md_path = output_file.with_suffix(".md")
        md_path.write_text(report.to_markdown(), encoding="utf-8")
        logger.info(
            "Markdown report written",
            extra={"path": str(md_path)},
        )
    else:
        print(report_json)

    # Print console summary
    emergency_count = _count_emergency_items(observations)
    print(f"\n=== Credential Discovery Summary ===", file=sys.stderr)
    print(f"Run ID: {run_id}", file=sys.stderr)
    print(f"Namespace: {namespace}", file=sys.stderr)
    print(f"Package version: {PACKAGE_VERSION}", file=sys.stderr)
    print(f"Observations: {len(observations)}", file=sys.stderr)
    print(f"Emergency items: {emergency_count}", file=sys.stderr)
    print(f"Coverage: {coverage}", file=sys.stderr)
    print(f"Entries SHA-256: {report.entries_sha256}", file=sys.stderr)

    if emergency_count > 0:
        print(f"\n=== EMERGENCY REMEDIATION ITEMS ===", file=sys.stderr)
        for item in _format_emergency_items(observations):
            print(item, file=sys.stderr)
        print(
            f"\nThese credentials are exposed as plaintext in workload "
            f"specifications and require immediate rotation.",
            file=sys.stderr,
        )
        return 2

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for run_discovery."""
    parser = argparse.ArgumentParser(
        prog="platform_orchestration_contracts.run_discovery",
        description="Run a one-shot credential discovery scan (Phase 1).",
    )
    parser.add_argument(
        "--namespace",
        required=True,
        help="Kubernetes namespace to scan (e.g. cts)",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["kubernetes"],
        help="Discovery sources to enable (only kubernetes is implemented)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write JSON posture report (stdout if omitted)",
    )
    parser.add_argument(
        "--environment",
        default="dev",
        help="Environment label for observations",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Unique run identifier (auto-generated if omitted)",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["WARNING", "INFO", "DEBUG"],
        help="Logging level (default: WARNING)",
    )

    args = parser.parse_args(argv)

    return run_discovery(
        namespace=args.namespace,
        sources=args.sources,
        output_path=args.output,
        environment=args.environment,
        run_id=args.run_id,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    sys.exit(main())

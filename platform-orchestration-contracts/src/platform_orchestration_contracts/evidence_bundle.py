"""Evidence bundle writer for credential discovery reports.

Provides atomic, safety-validated writing of discovery evidence bundles
to a destination directory. Every file written passes through
assert_safe_report_text() before reaching persistent storage.

The bundle layout is:

    destination/
      report.json
      report.md
      manifest.json
      checksums.txt

The write is atomic: all files are written to a temporary directory
that is a SIBLING of the final destination (same filesystem/PVC),
validated, then the temporary directory is renamed to the final
destination. If any safety check fails, no files are written.

Collision handling: if the destination already exists with the same
run_id and matching checksums, the write is treated as a safe replay
and the existing bundle is returned. If the destination exists with
a different run_id or mismatched content, an EvidenceBundleCollisionError
is raised — a retry or reused run_id must never silently overwrite
prior evidence.

This module is designed for the one-shot CTS discovery scan but is
generic enough for any discovery run that produces a PostureReport.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import __version__ as PACKAGE_VERSION
from .credential_discovery_workflow import PostureReport
from .observation_safety import UnsafeObservationError, assert_safe_report_text

logger = logging.getLogger("platform_orchestration_contracts.evidence_bundle")

EVIDENCE_MANIFEST_VERSION = "credential-discovery-evidence.v1"

# Closed vocabulary for scan_status in the evidence manifest.
SCAN_STATUS_COMPLETED = "completed"
SCAN_STATUS_COMPLETED_WITH_FINDINGS = "completed_with_findings"
SCAN_STATUS_FAILED = "failed"
SCAN_STATUS_PARTIAL = "partial"

_ALL_SCAN_STATUSES = frozenset({
    SCAN_STATUS_COMPLETED,
    SCAN_STATUS_COMPLETED_WITH_FINDINGS,
    SCAN_STATUS_FAILED,
    SCAN_STATUS_PARTIAL,
})


class EvidenceBundleCollisionError(RuntimeError):
    """Raised when an evidence bundle destination already exists with
    different content or a different run_id.

    This prevents silent overwrites from retries, manual reruns, or
    reused run IDs. The error message contains only opaque paths and
    run IDs — never report content.
    """

    def __init__(self, destination: str, existing_run_id: str, requested_run_id: str):
        self.destination = destination
        self.existing_run_id = existing_run_id
        self.requested_run_id = requested_run_id
        super().__init__(
            f"Evidence bundle collision at {destination}: "
            f"existing run_id={existing_run_id!r}, "
            f"requested run_id={requested_run_id!r}"
        )


def _sha256_hex(text: str) -> str:
    """Compute SHA-256 hex digest of a text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _determine_scan_status(exit_code: int, emergency_items: int) -> str:
    """Map exit code and emergency count to scan_status vocabulary.

    | Exit code | Emergency items | scan_status |
    |-----------|-----------------|-------------|
    | 0         | 0               | completed   |
    | 2         | >0              | completed_with_findings |
    | 1         | any             | failed      |
    | other     | any             | failed      |
    """
    if exit_code == 0 and emergency_items == 0:
        return SCAN_STATUS_COMPLETED
    if exit_code == 2 or (exit_code == 0 and emergency_items > 0):
        return SCAN_STATUS_COMPLETED_WITH_FINDINGS
    return SCAN_STATUS_FAILED


def build_evidence_manifest(
    *,
    report: PostureReport,
    report_json: str,
    report_markdown: str,
    generated_at: Optional[str] = None,
    exit_code: int = 0,
    scan_status: Optional[str] = None,
) -> str:
    """Build the evidence manifest JSON for a discovery run.

    The manifest includes checksums of all bundle files, package and
    policy versions, coverage status, scan result status, and exit
    code. It does NOT include report entries — those live in report.json.

    The scan_status field uses a closed vocabulary:
    - "completed": scan succeeded, no emergency findings
    - "completed_with_findings": scan succeeded, emergency items found
    - "failed": scan failed (API error, validation error)
    - "partial": scan partially completed (not used in Phase 1)

    This distinction matters because Kubernetes marks any non-zero
    exit code as a failed Job, but exit code 2 (findings detected) is
    a successful security control outcome, not a scanner failure.

    Args:
        report: The PostureReport that was generated.
        report_json: The rendered JSON report text.
        report_markdown: The rendered Markdown report text.
        generated_at: Optional timestamp. If None, uses current UTC.
        exit_code: Process exit code (0, 1, or 2).
        scan_status: Optional explicit status. If None, derived from
            exit_code and emergency_items count.

    Returns:
        JSON string of the evidence manifest.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()

    emergency_items = sum(
        1 for e in report.entries
        if e.exposure_status == "active_in_source"
        or e.recommended_next_action == "emergency_rotation"
    )

    if scan_status is None:
        scan_status = _determine_scan_status(exit_code, emergency_items)
    elif scan_status not in _ALL_SCAN_STATUSES:
        raise ValueError(
            f"scan_status must be one of {_ALL_SCAN_STATUSES}, got: {scan_status!r}"
        )

    manifest = {
        "manifest_version": EVIDENCE_MANIFEST_VERSION,
        "run_id": report.run_id,
        "generated_at": generated_at,
        "scan_status": scan_status,
        "exit_code": exit_code,
        "report_json_sha256": f"sha256:{_sha256_hex(report_json)}",
        "report_markdown_sha256": f"sha256:{_sha256_hex(report_markdown)}",
        "entries_sha256": report.entries_sha256,
        "package_version": PACKAGE_VERSION,
        "policy_version": report.policy_version,
        "report_version": report.report_version,
        "coverage": dict(report.coverage),
        "total_credentials": report.total_credentials,
        "emergency_items": emergency_items,
    }
    return json.dumps(manifest, sort_keys=True, indent=2)


def build_checksums_text(
    *,
    report_json: str,
    report_markdown: str,
    manifest_json: str,
) -> str:
    """Build a checksums.txt file listing SHA-256 of each bundle file.

    Format: one line per file: <sha256>  <filename>
    """
    lines = [
        f"{_sha256_hex(report_json)}  report.json",
        f"{_sha256_hex(report_markdown)}  report.md",
        f"{_sha256_hex(manifest_json)}  manifest.json",
    ]
    return "\n".join(lines) + "\n"


def _verify_bundle_matches(
    destination: Path,
    expected_files: dict[str, str],
) -> bool:
    """Check if an existing bundle's content matches the expected files.

    Compares file contents byte-for-byte. Returns True if all files
    match, False otherwise.
    """
    for name, expected_content in expected_files.items():
        existing_path = destination / name
        if not existing_path.exists():
            return False
        if existing_path.read_text(encoding="utf-8") != expected_content:
            return False
    return True


def _verify_bundle_idempotent(
    destination: Path,
    run_id: str,
    expected_report_json: str,
    expected_report_markdown: str,
) -> bool:
    """Check if an existing bundle is a safe replay for the same run.

    Unlike _verify_bundle_matches, this allows the manifest.json and
    checksums.txt to differ in timestamp while requiring that:
    1. The existing manifest has the same run_id.
    2. The report.json content matches exactly.
    3. The report.md content matches exactly.

    This handles Temporal retries and manual reruns where the report
    content is identical but the generated_at timestamp differs.
    """
    manifest_path = destination / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if existing_manifest.get("run_id") != run_id:
        return False

    # Verify report content matches
    report_json_path = destination / "report.json"
    if not report_json_path.exists():
        return False
    if report_json_path.read_text(encoding="utf-8") != expected_report_json:
        return False

    report_md_path = destination / "report.md"
    if not report_md_path.exists():
        return False
    if report_md_path.read_text(encoding="utf-8") != expected_report_markdown:
        return False

    return True


def write_safe_evidence_bundle(
    *,
    destination: Path,
    files: dict[str, str],
    run_id: Optional[str] = None,
) -> None:
    """Write an evidence bundle atomically with safety validation.

    Every file content is validated through assert_safe_report_text()
    before any write occurs. All files are written to a temporary
    directory that is a SIBLING of the destination (same filesystem),
    then the temporary directory is atomically renamed to the
    destination. If any safety check fails, no files are written.

    Collision handling:
    - If the destination already exists and the content matches
      (verified by reading and comparing all files), the write is
      treated as a safe replay and the existing bundle is preserved.
    - If the destination exists with different content, an
      EvidenceBundleCollisionError is raised.
    - This prevents retries, manual reruns, or reused run IDs from
      silently overwriting prior evidence.

    The temporary directory is created with `with_name()` to ensure
    it is a sibling of the destination on the same filesystem/PVC.
    This guarantees the rename is atomic and not a cross-device copy.

    Args:
        destination: Directory path for the evidence bundle.
        files: Mapping of filename → content. Each content string is
            safety-validated before writing.
        run_id: Optional run_id for collision error messages.

    Raises:
        UnsafeObservationError: If any file content contains prohibited
            secret-like material. No files are written.
        EvidenceBundleCollisionError: If the destination already exists
            with different content.
    """
    # Validate ALL files before writing ANY
    for name, content in files.items():
        assert_safe_report_text(content, context=f"evidence:{name}")

    # Create parent directory if needed
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Collision handling: check if destination already exists
    if destination.exists():
        if _verify_bundle_matches(destination, files):
            # Safe replay: identical content already persisted
            logger.info(
                "Evidence bundle already exists with identical content (safe replay)",
                extra={"destination": str(destination), "run_id": run_id or ""},
            )
            return
        # Collision: different content at same path
        existing_manifest_path = destination / "manifest.json"
        existing_run_id = "unknown"
        if existing_manifest_path.exists():
            try:
                existing_manifest = json.loads(
                    existing_manifest_path.read_text(encoding="utf-8")
                )
                existing_run_id = existing_manifest.get("run_id", "unknown")
            except (json.JSONDecodeError, OSError):
                pass
        raise EvidenceBundleCollisionError(
            destination=str(destination),
            existing_run_id=existing_run_id,
            requested_run_id=run_id or "unknown",
        )

    # Write to temporary directory for atomicity.
    # Using with_name() ensures the temp dir is a sibling of the
    # destination on the same filesystem/PVC, so the rename is atomic
    # and not a cross-device copy.
    tmp_dir = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        for name, content in files.items():
            (tmp_dir / name).write_text(content, encoding="utf-8")
        # Atomic rename (same filesystem)
        tmp_dir.rename(destination)
    except Exception:
        # Clean up temp dir on failure
        if tmp_dir.exists():
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    logger.info(
        "Evidence bundle written",
        extra={
            "destination": str(destination),
            "files": list(files.keys()),
            "run_id": run_id or "",
        },
    )


def write_discovery_evidence(
    *,
    base_path: Path,
    run_id: str,
    environment: str,
    report: PostureReport,
    exit_code: int = 0,
    scan_status: Optional[str] = None,
) -> Path:
    """Write a complete discovery evidence bundle with per-run layout.

    Creates a directory structure:
        base_path/
          credential-discovery/
            environment=<env>/
              run_id=<run_id>/
                report.json
                report.md
                manifest.json
                checksums.txt

    All files are safety-validated before writing. The write is atomic.
    Collision handling prevents silent overwrites of prior evidence.

    Idempotency: if the destination already exists with the same run_id
    and identical report.json/report.md content, the write is treated as
    a safe replay (e.g. from a Temporal retry) and the existing bundle
    is preserved. The manifest timestamp may differ — only the report
    content must match.

    Args:
        base_path: Base evidence directory (e.g. /evidence).
        run_id: Unique run identifier.
        environment: Environment label (e.g. "dev").
        report: The PostureReport to persist.
        exit_code: Process exit code for the manifest (default: 0).
        scan_status: Optional explicit scan status. If None, derived
            from exit_code and emergency item count.

    Returns:
        Path to the written evidence bundle directory.

    Raises:
        UnsafeObservationError: If any report content contains
            prohibited secret-like material.
        EvidenceBundleCollisionError: If the destination already exists
            with different content or a different run_id.
    """
    report_json = report.to_json()
    report_md = report.to_markdown()

    destination = (
        Path(base_path)
        / "credential-discovery"
        / f"environment={environment}"
        / f"run_id={run_id}"
    )

    # Idempotency check: if the destination exists with the same run_id
    # and identical report content, treat as a safe replay.
    if destination.exists():
        if _verify_bundle_idempotent(destination, run_id, report_json, report_md):
            logger.info(
                "Evidence bundle already exists with identical report content (safe replay)",
                extra={"destination": str(destination), "run_id": run_id},
            )
            return destination
        # Collision: different content or different run_id
        existing_manifest_path = destination / "manifest.json"
        existing_run_id = "unknown"
        if existing_manifest_path.exists():
            try:
                existing_manifest = json.loads(
                    existing_manifest_path.read_text(encoding="utf-8")
                )
                existing_run_id = existing_manifest.get("run_id", "unknown")
            except (json.JSONDecodeError, OSError):
                pass
        raise EvidenceBundleCollisionError(
            destination=str(destination),
            existing_run_id=existing_run_id,
            requested_run_id=run_id,
        )

    manifest_json = build_evidence_manifest(
        report=report,
        report_json=report_json,
        report_markdown=report_md,
        exit_code=exit_code,
        scan_status=scan_status,
    )
    checksums = build_checksums_text(
        report_json=report_json,
        report_markdown=report_md,
        manifest_json=manifest_json,
    )

    files = {
        "report.json": report_json,
        "report.md": report_md,
        "manifest.json": manifest_json,
        "checksums.txt": checksums,
    }

    write_safe_evidence_bundle(destination=destination, files=files, run_id=run_id)
    return destination

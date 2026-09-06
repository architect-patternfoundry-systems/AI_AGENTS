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

The write is atomic: all files are written to a temporary directory,
validated, then the temporary directory is renamed to the final
destination. If any safety check fails, no files are written.

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


def _sha256_hex(text: str) -> str:
    """Compute SHA-256 hex digest of a text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_evidence_manifest(
    *,
    report: PostureReport,
    report_json: str,
    report_markdown: str,
    generated_at: Optional[str] = None,
) -> str:
    """Build the evidence manifest JSON for a discovery run.

    The manifest includes checksums of all bundle files, package and
    policy versions, and coverage status. It does NOT include report
    entries — those live in report.json.

    Args:
        report: The PostureReport that was generated.
        report_json: The rendered JSON report text.
        report_markdown: The rendered Markdown report text.
        generated_at: Optional timestamp. If None, uses current UTC.

    Returns:
        JSON string of the evidence manifest.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()

    manifest = {
        "manifest_version": EVIDENCE_MANIFEST_VERSION,
        "run_id": report.run_id,
        "generated_at": generated_at,
        "report_json_sha256": f"sha256:{_sha256_hex(report_json)}",
        "report_markdown_sha256": f"sha256:{_sha256_hex(report_markdown)}",
        "entries_sha256": report.entries_sha256,
        "package_version": PACKAGE_VERSION,
        "policy_version": report.policy_version,
        "report_version": report.report_version,
        "coverage": dict(report.coverage),
        "total_credentials": report.total_credentials,
        "emergency_items": sum(
            1 for e in report.entries
            if e.recommended_next_action == "emergency_rotation"
        ),
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


def write_safe_evidence_bundle(
    *,
    destination: Path,
    files: dict[str, str],
) -> None:
    """Write an evidence bundle atomically with safety validation.

    Every file content is validated through assert_safe_report_text()
    before any write occurs. All files are written to a temporary
    directory first, then the directory is atomically renamed to the
    destination. If any safety check fails, no files are written.

    Args:
        destination: Directory path for the evidence bundle.
        files: Mapping of filename → content. Each content string is
            safety-validated before writing.

    Raises:
        UnsafeObservationError: If any file content contains prohibited
            secret-like material. No files are written.
        FileExistsError: If the destination already exists.
    """
    # Validate ALL files before writing ANY
    for name, content in files.items():
        assert_safe_report_text(content, context=f"evidence:{name}")

    # Create parent directory if needed
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary directory for atomicity
    tmp_dir = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        for name, content in files.items():
            (tmp_dir / name).write_text(content, encoding="utf-8")
        # Atomic rename
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
        },
    )


def write_discovery_evidence(
    *,
    base_path: Path,
    run_id: str,
    environment: str,
    report: PostureReport,
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

    Args:
        base_path: Base evidence directory (e.g. /evidence).
        run_id: Unique run identifier.
        environment: Environment label (e.g. "dev").
        report: The PostureReport to persist.

    Returns:
        Path to the written evidence bundle directory.

    Raises:
        UnsafeObservationError: If any report content contains
            prohibited secret-like material.
    """
    report_json = report.to_json()
    report_md = report.to_markdown()
    manifest_json = build_evidence_manifest(
        report=report,
        report_json=report_json,
        report_markdown=report_md,
    )
    checksums = build_checksums_text(
        report_json=report_json,
        report_markdown=report_md,
        manifest_json=manifest_json,
    )

    destination = (
        Path(base_path)
        / "credential-discovery"
        / f"environment={environment}"
        / f"run_id={run_id}"
    )

    files = {
        "report.json": report_json,
        "report.md": report_md,
        "manifest.json": manifest_json,
        "checksums.txt": checksums,
    }

    write_safe_evidence_bundle(destination=destination, files=files)
    return destination

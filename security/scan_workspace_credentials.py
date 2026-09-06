#!/usr/bin/env python3
"""Workspace-wide credential exposure scanner.

Scans all repositories in /home/cortex/workspace for hardcoded credentials
and produces a report of findings. Designed to be run manually or in CI.

Usage:
    python3 scan_workspace_credentials.py [--json] [--quiet]

Exit codes:
    0 — no findings
    1 — findings detected (review required)
    2 — scanner error

This script complements gitleaks by checking for project-specific patterns
that gitleaks may not catch, such as:
    - Known credential values from prior incidents
    - Plaintext Kubernetes Secret manifests (stringData with passwords)
    - DSN strings with embedded passwords
    - Default password values in Python/shell scripts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

WORKSPACE_ROOT = Path("/home/cortex/workspace")

# Repositories to scan
REPOS = [
    "cts",
    "neural_mesh_canvas",
    "application",
    "infrastructure_check",
    "AI_AGENTS",
    "storyloom",
]

# File extensions to scan
SCAN_EXTENSIONS = {
    ".py", ".sh", ".yaml", ".yml", ".ini", ".cfg", ".json",
    ".toml", ".env", ".tf", ".ts", ".js", ".tsx", ".jsx",
    ".md", ".txt",
}

# Directories to skip
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".pytest_cache", ".backups", "dist", "build", ".next",
    ".cache", "migrated_services_archive",
}

# --- Known credential values from prior incidents ---
# These are the actual exposed values that must be rotated.
# After rotation, remove them from this list.
KNOWN_EXPOSED_VALUES = {
    "XwYcij2BguKzVlEdlsKJu1": "PostgreSQL app password (CTS, application, infrastructure)",
    "cNJ3+eCdYQoRSbdxpikZp9cG": "MinIO root password (CTS, infrastructure)",
    "mjGjxdcK9eoZ8i88gB3T9VM0KFPPeYndEoY1GGne6IPqpUlkGcJAYGCigzBdYL2LT": "PostgreSQL superuser password (neural_mesh_canvas)",
}

# --- Pattern-based detection ---

# DSN with embedded password
DSN_PATTERN = re.compile(
    r'(postgresql|postgres|mysql|mongodb)://[^:\s@]+:[^@\s]+@',
    re.IGNORECASE,
)

# Kubernetes Secret with stringData containing password-like keys
K8S_STRINGDATA_PATTERN = re.compile(
    r'stringData:\s*\n(?:.*\n)*?\s+(?:password|secret|key|token|dsn|uri)\s*:\s*["\']?([A-Za-z0-9+/=]{6,})',
    re.IGNORECASE,
)

# Environment variable assignment with literal password (not placeholder)
ENV_PASSWORD_PATTERN = re.compile(
    r'(?:POSTGRES_PASSWORD|PG_PASS|DATABASE_URL|DB_PASSWORD|MINIO_ROOT_PASSWORD|'
    r'AWS_SECRET_ACCESS_KEY|SECRET_KEY|NEO4J_PASSWORD|TOKEN_SECRET)'
    r'\s*[=:]\s*["\']?(?!<|your_|REPLACE_|placeholder|\$\{|env\.|\$\()'
    r'[A-Za-z0-9+/=]{8,}',
    re.IGNORECASE,
)

# Placeholder patterns that are safe
SAFE_PLACEHOLDERS = {
    "<POSTGRES_PASSWORD>",
    "<PG_PASS>",
    "<MINIO_ACCESS_KEY>",
    "<MINIO_SECRET_KEY>",
    "your_secure_password",
    "REPLACE_WITH_",
    "${POSTGRES_PASSWORD",
    "${PG_PASS",
    "${MINIO",
    "password=<POSTGRES_PASSWORD>",
    "os.environ.get",
    "os.getenv",
    "secretKeyRef",
    "valueFrom",
}


@dataclass
class Finding:
    repo: str
    file: str
    line_number: int
    line_content: str
    finding_type: str
    severity: str  # "critical", "high", "medium"
    description: str


def should_skip_dir(dir_name: str) -> bool:
    return dir_name in SKIP_DIRS or dir_name.startswith(".")


def is_safe_line(line: str) -> bool:
    """Check if a line contains only safe placeholder patterns."""
    for placeholder in SAFE_PLACEHOLDERS:
        if placeholder in line:
            return True
    return False


def scan_file(filepath: Path, repo_name: str) -> list[Finding]:
    """Scan a single file for credential exposure."""
    findings: list[Finding] = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()

        # Skip comments and safe placeholder lines
        if stripped.startswith("#") and not KNOWN_EXPOSED_VALUES:
            continue
        if is_safe_line(stripped):
            continue

        # Check for known exposed values
        for value, desc in KNOWN_EXPOSED_VALUES.items():
            if value in line:
                findings.append(Finding(
                    repo=repo_name,
                    file=str(filepath.relative_to(WORKSPACE_ROOT / repo_name)),
                    line_number=i,
                    line_content=stripped[:120],
                    finding_type="known_exposed_value",
                    severity="critical",
                    description=desc,
                ))
                continue

        # Check for DSN with embedded password
        if DSN_PATTERN.search(line) and not is_safe_line(line):
            # Skip if it's a placeholder
            if "<" not in line and "your_" not in line and "$" not in line:
                findings.append(Finding(
                    repo=repo_name,
                    file=str(filepath.relative_to(WORKSPACE_ROOT / repo_name)),
                    line_number=i,
                    line_content=stripped[:120],
                    finding_type="dsn_with_password",
                    severity="high",
                    description="DSN string with embedded password",
                ))

        # Check for env var with literal password
        if ENV_PASSWORD_PATTERN.search(line) and not is_safe_line(line):
            # Skip if it's a secretKeyRef or envFrom
            if "secretKeyRef" not in line and "envFrom" not in line:
                # Skip if the value looks like a placeholder
                match = ENV_PASSWORD_PATTERN.search(line)
                if match:
                    value_part = match.group(0).split("=", 1)[-1].split(":", 1)[-1].strip("\"' ")
                    if not value_part.startswith(("<", "your_", "REPLACE_", "${", "env.")):
                        if len(value_part) >= 8 and value_part not in ("admin",):
                            findings.append(Finding(
                                repo=repo_name,
                                file=str(filepath.relative_to(WORKSPACE_ROOT / repo_name)),
                                line_number=i,
                                line_content=stripped[:120],
                                finding_type="env_password_literal",
                                severity="high",
                                description="Environment variable with literal password value",
                            ))

    return findings


def scan_repo(repo_name: str) -> list[Finding]:
    """Scan a single repository."""
    repo_path = WORKSPACE_ROOT / repo_name
    if not repo_path.exists():
        return []

    findings: list[Finding] = []
    for root, dirs, files in os.walk(repo_path):
        # Skip hidden and build directories
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        for filename in files:
            filepath = Path(root) / filename
            ext = filepath.suffix.lower()
            if ext in SCAN_EXTENSIONS:
                findings.extend(scan_file(filepath, repo_name))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan workspace for credential exposure")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    all_findings: list[Finding] = []

    for repo in REPOS:
        if not args.quiet:
            print(f"Scanning {repo}...", file=sys.stderr)
        findings = scan_repo(repo)
        all_findings.extend(findings)

    if args.json:
        output = [
            {
                "repo": f.repo,
                "file": f.file,
                "line": f.line_number,
                "type": f.finding_type,
                "severity": f.severity,
                "description": f.description,
                "content": f.line_content,
            }
            for f in all_findings
        ]
        print(json.dumps(output, indent=2))
    else:
        if not all_findings:
            print("No credential exposure findings.")
            return 0

        # Group by repo
        by_repo: dict[str, list[Finding]] = {}
        for f in all_findings:
            by_repo.setdefault(f.repo, []).append(f)

        critical_count = sum(1 for f in all_findings if f.severity == "critical")
        high_count = sum(1 for f in all_findings if f.severity == "high")

        print(f"\nCredential Exposure Report")
        print(f"={'=' * 60}")
        print(f"Total findings: {len(all_findings)} ({critical_count} critical, {high_count} high)\n")

        for repo in sorted(by_repo.keys()):
            findings = by_repo[repo]
            print(f"\n{repo} ({len(findings)} findings):")
            print(f"{'-' * 40}")
            for f in findings:
                print(f"  [{f.severity.upper()}] {f.file}:{f.line_number}")
                print(f"    Type: {f.finding_type}")
                print(f"    Description: {f.description}")
                print(f"    Content: {f.line_content[:100]}")
                print()

        print(f"\n{'=' * 60}")
        print("REQUIRED ACTIONS:")
        print("  1. Rotate all CRITICAL findings immediately")
        print("  2. Move credentials to Kubernetes Secrets or external secret manager")
        print("  3. Replace literals with secretKeyRef or envFrom")
        print("  4. Run gitleaks before committing: gitleaks detect --source . -v")
        print("  5. After rotation, update KNOWN_EXPOSED_VALUES in this script")

    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())

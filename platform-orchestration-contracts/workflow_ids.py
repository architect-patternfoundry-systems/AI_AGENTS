"""Workflow ID conventions.

Deterministic workflow ID construction following ADR-036 section 3.3:

    <domain>:<operation>:<business-id>

Examples:
    cts:ingest:job_20260903211130_5_q
    casting:corpus-batch:batch_01JABC
    nexus:publish:asset_01JXYZ
    media:transcode:artifact_sha256_...

Child workflows append a scoped qualifier:

    casting:corpus-batch:batch_01JABC:locale:en
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Domains — extend cautiously; each domain implies an owning application.
VALID_DOMAINS = frozenset(
    {
        "cts",
        "casting",
        "nexus",
        "media",
        "toneroot",
    }
)

# Pattern for a single ID segment: alphanumeric, underscore, hyphen, dot.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

# Full workflow ID pattern: domain:operation:business-id[:scope:scope-value]...
_WORKFLOW_ID_RE = re.compile(
    r"^(?P<domain>[a-z]+):(?P<operation>[a-z0-9\-]+):(?P<business_id>[A-Za-z0-9][A-Za-z0-9_.\-]*)"
    r"(?P<scopes>(?::[A-Za-z0-9][A-Za-z0-9_.\-]*:[A-Za-z0-9][A-Za-z0-9_.\-]*)*)$"
)


def build_workflow_id(domain: str, operation: str, business_id: str) -> str:
    """Construct a canonical workflow ID.

    Raises ValueError if domain is unknown or any segment is malformed.
    """
    if domain not in VALID_DOMAINS:
        raise ValueError(
            f"Unknown domain {domain!r}; expected one of {sorted(VALID_DOMAINS)}"
        )
    if not _SEGMENT_RE.match(operation):
        raise ValueError(f"Invalid operation segment {operation!r}")
    if not _SEGMENT_RE.match(business_id):
        raise ValueError(f"Invalid business_id segment {business_id!r}")
    return f"{domain}:{operation}:{business_id}"


def build_child_workflow_id(
    parent_workflow_id: str, scope_key: str, scope_value: str
) -> str:
    """Append a scoped qualifier to a parent workflow ID.

    Example:
        parent = "casting:corpus-batch:batch_01JABC"
        build_child_workflow_id(parent, "locale", "en")
        -> "casting:corpus-batch:batch_01JABC:locale:en"
    """
    if not _SEGMENT_RE.match(scope_key):
        raise ValueError(f"Invalid scope_key {scope_key!r}")
    if not _SEGMENT_RE.match(scope_value):
        raise ValueError(f"Invalid scope_value {scope_value!r}")
    return f"{parent_workflow_id}:{scope_key}:{scope_value}"


@dataclass(frozen=True)
class ParsedWorkflowId:
    """Decomposed workflow ID."""

    domain: str
    operation: str
    business_id: str
    scopes: tuple[tuple[str, str], ...]  # (("locale", "en"), ("voice", "primary"))


def parse_workflow_id(workflow_id: str) -> ParsedWorkflowId:
    """Parse a canonical workflow ID into its components.

    Raises ValueError if the ID does not match the canonical pattern.
    """
    m = _WORKFLOW_ID_RE.match(workflow_id)
    if not m:
        raise ValueError(f"Invalid workflow ID {workflow_id!r}")
    scopes_str = m.group("scopes") or ""
    scopes: list[tuple[str, str]] = []
    if scopes_str:
        parts = scopes_str.split(":")
        # parts[0] is empty (leading colon); pairs follow
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                scopes.append((parts[i], parts[i + 1]))
    return ParsedWorkflowId(
        domain=m.group("domain"),
        operation=m.group("operation"),
        business_id=m.group("business_id"),
        scopes=tuple(scopes),
    )

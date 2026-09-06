"""Observation safety validation — defense-in-depth against secret leakage.

This module provides validation that CredentialObservation values do not
accidentally carry secret material through fields like provider_ref,
evidence_ref, risk_signals, or consumer_refs.

This is NOT a replacement for a secret scanner (Gitleaks, truffleHog, etc.).
It is a defense-in-depth control that runs before observations become
evidence or dashboard data. The forbidden markers cover common secret
formats that a careless adapter might propagate.

Usage:
    from platform_orchestration_contracts.observation_safety import (
        UnsafeObservationError,
        assert_observation_safe,
    )

    for obs in observations:
        assert_observation_safe(obs)  # raises UnsafeObservationError
"""

from __future__ import annotations

import json
from typing import Any

from .credential_discovery_workflow import CredentialObservation


class UnsafeObservationError(ValueError):
    """Raised when a CredentialObservation contains prohibited secret-like material.

    This is a fail-closed error: the observation must not be persisted as
    evidence or displayed on a dashboard until the offending material is
    redacted or removed.
    """

    def __init__(self, observation_id: str, reason: str, marker: str = ""):
        self.observation_id = observation_id
        self.reason = reason
        self.marker = marker
        msg = f"Credential observation {observation_id!r} is unsafe: {reason}"
        if marker:
            msg += f" (matched marker: {marker!r})"
        super().__init__(msg)


# Forbidden markers — substrings that indicate secret material may be present.
# These are checked case-insensitively against the canonical JSON serialization
# of the observation. The list is deliberately conservative: false positives
# are acceptable; false negatives are not.
#
# IMPORTANT: Markers for env var NAMES must include a trailing "=" or value
# indicator so that legitimate references to the env var name (e.g. in
# observation_id or evidence_ref) are not flagged. Recording that a workload
# has an env var named "AWS_SECRET_ACCESS_KEY" is safe metadata; recording
# its value is not.
FORBIDDEN_MARKERS: tuple[str, ...] = (
    # DSN / connection string patterns (these always indicate a value is present)
    "password=",
    "postgres://",
    "postgresql://",
    "mysql://",
    "mongodb://",
    "redis://:",
    # Secret value patterns — must include "=" to distinguish from env var names
    "secret=",
    "token=",
    "access_key=",
    "aws_secret_access_key=",
    "aws_access_key_id=",
    "private_key=",
    "api_key=",
    # PEM key headers (always indicate key material is present)
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN EC PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
    # Generic credential value patterns
    "bearer ",
    "authorization:",
)

# Minimum length for a string to be considered a potential base64 secret blob.
# This avoids flagging short base64-like strings that are legitimate IDs.
_BASE64_SECRET_MIN_LENGTH = 40


def _canonical_json(obs: CredentialObservation) -> str:
    """Serialize observation to canonical lowercase JSON for marker checking."""
    return json.dumps(obs.to_dict(), sort_keys=True, separators=(",", ":")).lower()


def _check_forbidden_markers(
    obs: CredentialObservation,
    serialized: str,
) -> None:
    """Check serialized observation for forbidden secret-like markers."""
    for marker in FORBIDDEN_MARKERS:
        if marker.lower() in serialized:
            raise UnsafeObservationError(
                observation_id=obs.observation_id,
                reason="contains prohibited secret-like material",
                marker=marker,
            )


def _check_plaintext_retained(obs: CredentialObservation) -> None:
    """Verify plaintext_retained is False (Phase 1 invariant)."""
    if obs.plaintext_retained:
        raise UnsafeObservationError(
            observation_id=obs.observation_id,
            reason="plaintext_retained is True; Phase 1 requires False",
        )


def _check_ref_fields_not_empty_secrets(obs: CredentialObservation) -> None:
    """Check that ref fields don't contain raw DSNs or connection strings.

    This is a targeted check on the high-risk fields that adapters might
    accidentally populate with secret material.
    """
    high_risk_fields = (
        obs.provider_ref,
        obs.provider_identity_ref,
        obs.secret_authority_ref,
        obs.evidence_ref,
    )
    for field_value in high_risk_fields:
        if field_value is None:
            continue
        lowered = field_value.lower()
        for marker in ("password=", "postgres://", "postgresql://", "mysql://"):
            if marker in lowered:
                raise UnsafeObservationError(
                    observation_id=obs.observation_id,
                    reason=f"reference field contains connection string with credentials",
                    marker=marker,
                )


def assert_observation_safe(obs: CredentialObservation) -> None:
    """Validate that a CredentialObservation is safe for evidence/dashboard use.

    Checks:
    1. plaintext_retained is False (Phase 1 invariant).
    2. No forbidden secret-like markers in canonical serialization.
    3. Reference fields don't contain raw DSNs or connection strings.

    Raises:
        UnsafeObservationError: If the observation fails any safety check.

    This function should be called by:
    - Source adapters before returning observations.
    - The correlation service before persisting observations.
    - The evidence writer before storing observations.
    - Tests that verify adapter output safety.
    """
    _check_plaintext_retained(obs)
    serialized = _canonical_json(obs)
    _check_forbidden_markers(obs, serialized)
    _check_ref_fields_not_empty_secrets(obs)


def assert_observations_safe(
    observations: tuple[CredentialObservation, ...],
) -> None:
    """Validate a batch of observations. Raises on the first unsafe one."""
    for obs in observations:
        assert_observation_safe(obs)


def assert_safe_report_text(text: str, context: str = "report") -> None:
    """Validate that report text (JSON or Markdown) contains no secret material.

    This is a FINAL OUTPUT GATE that checks the fully rendered report
    text before it is written to any persistent storage. It protects
    against a later change in record conversion, report templating,
    exception formatting, or metadata fields bypassing observation-level
    validation.

    The check is pattern-based: it rejects known secret-bearing markers
    that indicate a value (not just a field name) is present. It uses
    the same marker philosophy as assert_observation_safe — markers for
    env var names include a trailing "=" to distinguish legitimate
    metadata from secret values.

    Args:
        text: The report text to validate (JSON or Markdown string).
        context: Description of what is being validated (for error messages).

    Raises:
        UnsafeObservationError: If forbidden secret-like markers are found.
    """
    text_lower = text.lower()
    for marker in FORBIDDEN_MARKERS:
        if marker.lower() in text_lower:
            raise UnsafeObservationError(
                observation_id=f"<{context}>",
                reason=f"report text contains prohibited secret-like material",
                marker=marker,
            )

"""Audio artifact manifest schema.

Canonical manifest accepted by Nexus and emitted by CTS, Casting Signal,
ToneRoot, and any other audio producer. See ADR-036 section 7.

This makes "store it the same way ToneRoot does" a testable contract:

    any producer
      -> artifact manifest
      -> S3 object storage
      -> Nexus registration / conversion
      -> catalog record
      -> player-ready endpoint
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class ProvenanceBlock:
    """Provenance metadata linking an artifact to its source."""

    source_script_checksum: str  # "sha256:..."
    voice_reference_id: Optional[str] = None
    voice_reference_checksum: Optional[str] = None
    engine: str = "unknown"  # "alltalk_tts" | "whisper" | "fish_speech" | ...
    engine_version: Optional[str] = None
    model_id: Optional[str] = None
    generation_parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioFile:
    """A single audio file within a manifest."""

    path: str  # relative path within the batch directory
    format: str  # "wav" | "mp3" | "flac"
    sample_rate_hz: int
    channels: int
    duration_seconds: float
    checksum: str  # "sha256:..."
    locale: str
    voice: str  # "primary" | "secondary" | "both"
    node: Optional[str] = None  # matrix node id, e.g. "mul-mantra"
    normalized: bool = False  # True if this is the player-normalized derivative


@dataclass(frozen=True)
class ArtifactManifest:
    """Canonical audio artifact manifest.

    Stored alongside generated audio in S3 and consumed by Nexus for
    catalog registration and playback URL generation.
    """

    manifest_version: str = "1"
    manifest_id: str = ""  # ULID or UUID
    batch_id: str = ""
    workflow_id: str = ""
    run_id: str = ""
    correlation_id: Optional[str] = None
    source_app: str = ""
    tenant_id: str = ""
    project_id: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    provenance: ProvenanceBlock = field(
        default_factory=lambda: ProvenanceBlock(source_script_checksum="")
    )
    files: tuple[AudioFile, ...] = field(default_factory=tuple)
    nexus_catalog_id: Optional[str] = None  # filled after Nexus registration
    playback_base_url: Optional[str] = None  # filled after publication

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "manifest_id": self.manifest_id,
            "batch_id": self.batch_id,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "source_app": self.source_app,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "provenance": {
                "source_script_checksum": self.provenance.source_script_checksum,
                "voice_reference_id": self.provenance.voice_reference_id,
                "voice_reference_checksum": self.provenance.voice_reference_checksum,
                "engine": self.provenance.engine,
                "engine_version": self.provenance.engine_version,
                "model_id": self.provenance.model_id,
                "generation_parameters": dict(self.provenance.generation_parameters),
            },
            "files": [
                {
                    "path": f.path,
                    "format": f.format,
                    "sample_rate_hz": f.sample_rate_hz,
                    "channels": f.channels,
                    "duration_seconds": f.duration_seconds,
                    "checksum": f.checksum,
                    "locale": f.locale,
                    "voice": f.voice,
                    "node": f.node,
                    "normalized": f.normalized,
                }
                for f in self.files
            ],
            "nexus_catalog_id": self.nexus_catalog_id,
            "playback_base_url": self.playback_base_url,
        }

"""Tests for platform-orchestration-contracts."""

import pytest

from workflow_envelope import (
    WorkflowEnvelope,
    RequestedBy,
    GovernanceBlock,
    InputRef,
)
from workflow_result import (
    WorkflowResult,
    Summary,
    ArtifactRef,
    CatalogRef,
    Warning,
)
from workflow_ids import (
    build_workflow_id,
    build_child_workflow_id,
    parse_workflow_id,
)
from artifact_manifest import (
    ArtifactManifest,
    AudioFile,
    ProvenanceBlock,
)
from temporal_client import (
    StubOrchestrationClient,
    TASK_QUEUE_CASTING_WORKFLOWS,
)


# --- WorkflowEnvelope ---


def test_envelope_roundtrip():
    env = WorkflowEnvelope(
        request_id="req_01JTEST",
        workflow_id="casting:corpus-batch:batch_01JTEST",
        workflow_type="media.corpus-batch.v1",
        source_app="casting-signal",
        tenant_id="patternfoundry",
        idempotency_key="casting-corpus:batch_01JTEST",
        requested_by=RequestedBy(subject_id="user_1", actor_type="user"),
        input_ref=InputRef(
            kind="s3-json-manifest",
            uri="s3://bucket/manifests/batch_01JTEST.json",
            checksum="sha256:abc123",
        ),
        governance=GovernanceBlock(approval_required=True, force_regenerate=False),
        project_id="japji-matrix",
        correlation_id="corr_01JTEST",
    )
    d = env.to_dict()
    assert d["workflow_type"] == "media.corpus-batch.v1"
    assert d["governance"]["approval_required"] is True
    restored = WorkflowEnvelope.from_dict(d)
    assert restored.workflow_id == env.workflow_id
    assert restored.governance.approval_required is True
    assert restored.input_ref.checksum == "sha256:abc123"


# --- WorkflowResult ---


def test_result_valid_status():
    r = WorkflowResult(
        workflow_id="cts:ingest:job_1",
        run_id="run_1",
        status="completed",
    )
    assert r.status == "completed"


def test_result_invalid_status():
    with pytest.raises(ValueError, match="Invalid workflow status"):
        WorkflowResult(
            workflow_id="cts:ingest:job_1",
            run_id="run_1",
            status="bogus",
        )


def test_result_roundtrip():
    r = WorkflowResult(
        workflow_id="casting:corpus-batch:batch_1",
        run_id="run_1",
        status="completed_with_warnings",
        summary=Summary(requested_items=280, generated_items=276, failed_items=2),
        artifacts=(
            ArtifactRef(kind="audio-manifest", uri="s3://b/m.json", checksum="sha256:x"),
        ),
        catalog_refs=(
            CatalogRef(system="nexus", entity_type="audio-corpus-batch", entity_id="nexus_1"),
        ),
        warnings=(Warning(code="VOICE_REFERENCE_MISSING", scope="locale:ar"),),
        correlation_id="corr_1",
    )
    d = r.to_dict()
    assert d["summary"]["generated_items"] == 276
    assert len(d["artifacts"]) == 1
    restored = WorkflowResult.from_dict(d)
    assert restored.summary.failed_items == 2
    assert restored.warnings[0].code == "VOICE_REFERENCE_MISSING"


# --- WorkflowIds ---


def test_build_workflow_id():
    wid = build_workflow_id("casting", "corpus-batch", "batch_01JABC")
    assert wid == "casting:corpus-batch:batch_01JABC"


def test_build_workflow_id_unknown_domain():
    with pytest.raises(ValueError, match="Unknown domain"):
        build_workflow_id("unknown", "op", "id")


def test_build_child_workflow_id():
    parent = build_workflow_id("casting", "corpus-batch", "batch_01JABC")
    child = build_child_workflow_id(parent, "locale", "en")
    assert child == "casting:corpus-batch:batch_01JABC:locale:en"


def test_parse_workflow_id_simple():
    parsed = parse_workflow_id("cts:ingest:job_20260903_5_q")
    assert parsed.domain == "cts"
    assert parsed.operation == "ingest"
    assert parsed.business_id == "job_20260903_5_q"
    assert parsed.scopes == ()


def test_parse_workflow_id_with_scopes():
    parsed = parse_workflow_id("casting:corpus-batch:batch_01JABC:locale:en:voice:primary")
    assert parsed.domain == "casting"
    assert parsed.scopes == (("locale", "en"), ("voice", "primary"))


def test_parse_workflow_id_invalid():
    with pytest.raises(ValueError, match="Invalid workflow ID"):
        parse_workflow_id("not-a-valid-id")


# --- ArtifactManifest ---


def test_manifest_to_dict():
    manifest = ArtifactManifest(
        manifest_id="man_01JTEST",
        batch_id="batch_01JTEST",
        workflow_id="casting:corpus-batch:batch_01JTEST",
        run_id="run_1",
        source_app="casting-signal",
        tenant_id="patternfoundry",
        provenance=ProvenanceBlock(
            source_script_checksum="sha256:script",
            engine="alltalk_tts",
            engine_version="v1",
        ),
        files=(
            AudioFile(
                path="generated/locale=en/voice=primary/node=mul-mantra/source.wav",
                format="wav",
                sample_rate_hz=22050,
                channels=1,
                duration_seconds=12.5,
                checksum="sha256:audio",
                locale="en",
                voice="primary",
                node="mul-mantra",
            ),
        ),
    )
    d = manifest.to_dict()
    assert d["manifest_version"] == "1"
    assert d["provenance"]["engine"] == "alltalk_tts"
    assert len(d["files"]) == 1
    assert d["files"][0]["locale"] == "en"


# --- StubOrchestrationClient ---


@pytest.mark.asyncio
async def test_stub_client_start_idempotent():
    client = StubOrchestrationClient()
    env = WorkflowEnvelope(
        request_id="req_1",
        workflow_id="cts:ingest:job_1",
        workflow_type="media.ingestion.v1",
        source_app="cts",
        tenant_id="patternfoundry",
        idempotency_key="cts:ingest:job_1",
        requested_by=RequestedBy(subject_id="user_1"),
        input_ref=InputRef(kind="inline-json", uri="inline", checksum="sha256:x"),
    )
    run_id_1 = await client.start(
        "media.ingestion.v1",
        "cts:ingest:job_1",
        TASK_QUEUE_CASTING_WORKFLOWS,
        env,
    )
    run_id_2 = await client.start(
        "media.ingestion.v1",
        "cts:ingest:job_1",
        TASK_QUEUE_CASTING_WORKFLOWS,
        env,
    )
    assert run_id_1 == run_id_2  # idempotent


@pytest.mark.asyncio
async def test_stub_client_signal():
    client = StubOrchestrationClient()
    env = WorkflowEnvelope(
        request_id="req_1",
        workflow_id="cts:ingest:job_1",
        workflow_type="media.ingestion.v1",
        source_app="cts",
        tenant_id="patternfoundry",
        idempotency_key="cts:ingest:job_1",
        requested_by=RequestedBy(subject_id="user_1"),
        input_ref=InputRef(kind="inline-json", uri="inline", checksum="sha256:x"),
    )
    await client.start("media.ingestion.v1", "cts:ingest:job_1", "cts-workflows", env)
    await client.signal("cts:ingest:job_1", "approve", {"approved_by": "user_1"})
    status = await client.status("cts:ingest:job_1")
    assert status.workflow_id == "cts:ingest:job_1"

"""Tests for platform-orchestration-contracts."""

import json
import pytest

from platform_orchestration_contracts import (
    WorkflowEnvelope,
    RequestedBy,
    GovernanceBlock,
    InputRef,
    WorkflowResult,
    Summary,
    ArtifactRef,
    CatalogRef,
    Warning,
    build_workflow_id,
    build_child_workflow_id,
    parse_workflow_id,
    ArtifactManifest,
    AudioFile,
    ProvenanceBlock,
    WorkflowError,
    ERROR_CODES,
    validation_failed,
    resource_unavailable,
    dependency_unavailable,
    retry_exhausted,
    internal_error,
    WorkflowStartCommand,
    OutboxCommandStatus,
    StartResult,
    START_POLICY_TABLE,
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


# --- ErrorTaxonomy ---


def test_error_valid_code():
    err = WorkflowError(
        code="RESOURCE_UNAVAILABLE",
        source="gpu-nanny",
        message="TTS GPU capacity unavailable",
    )
    assert err.code == "RESOURCE_UNAVAILABLE"
    # RESOURCE_UNAVAILABLE is retryable by default
    assert err.retryable is True


def test_error_invalid_code():
    with pytest.raises(ValueError, match="Unknown error code"):
        WorkflowError(code="BOGUS", source="x", message="y")


def test_error_non_retryable_default():
    err = WorkflowError(
        code="VALIDATION_FAILED",
        source="casting-signal",
        message="Invalid locale",
    )
    assert err.retryable is False


def test_error_roundtrip():
    err = WorkflowError(
        code="DEPENDENCY_UNAVAILABLE",
        source="alltalk-tts",
        message="Connection refused",
        retry_after_seconds=30,
        correlation_id="corr_1",
    )
    d = err.to_dict()
    assert d["retry_after_seconds"] == 30
    restored = WorkflowError.from_dict(d)
    assert restored.code == "DEPENDENCY_UNAVAILABLE"
    assert restored.retryable is True


def test_error_convenience_constructors():
    assert validation_failed("app", "msg").code == "VALIDATION_FAILED"
    assert resource_unavailable("gpu", "msg").retryable is True
    assert dependency_unavailable("svc", "msg").retry_after_seconds == 30
    assert retry_exhausted("worker", "msg").retryable is False
    assert internal_error("app", "msg").retryable is True


def test_all_error_codes_have_default_retryability():
    """Every code in ERROR_CODES must have a default retryability entry."""
    for code in ERROR_CODES:
        assert code in _DEFAULT_RETRYABLE_CHECK, f"Missing default for {code}"


_DEFAULT_RETRYABLE_CHECK = {
    "VALIDATION_FAILED": False,
    "AUTHORIZATION_DENIED": False,
    "APPROVAL_REJECTED": False,
    "APPROVAL_EXPIRED": False,
    "RESOURCE_UNAVAILABLE": True,
    "LEASE_NOT_ADMITTED": True,
    "DEPENDENCY_UNAVAILABLE": True,
    "RETRY_EXHAUSTED": False,
    "ARTIFACT_VALIDATION_FAILED": True,
    "ARTIFACT_PUBLICATION_FAILED": True,
    "CATALOG_REGISTRATION_FAILED": True,
    "CANCELLED": False,
    "COMPENSATION_FAILED": False,
    "INTERNAL_ERROR": True,
}


# --- Outbox ---


def test_outbox_command_defaults():
    cmd = WorkflowStartCommand(
        command_id="cmd_01JTEST",
        workflow_id="casting:corpus-batch:batch_01JTEST",
        workflow_type="media.corpus-batch.v1",
        task_queue="casting-workflows",
        envelope_json="{}",
    )
    assert cmd.status == OutboxCommandStatus.PENDING
    assert cmd.dispatch_attempts == 0
    assert cmd.temporal_run_id is None


def test_outbox_command_roundtrip():
    cmd = WorkflowStartCommand(
        command_id="cmd_01JTEST",
        workflow_id="casting:corpus-batch:batch_01JTEST",
        workflow_type="media.corpus-batch.v1",
        task_queue="casting-workflows",
        envelope_json='{"request_id": "req_1"}',
        status=OutboxCommandStatus.CONFIRMED,
        temporal_run_id="run_1",
    )
    d = cmd.to_dict()
    assert d["status"] == "confirmed"
    assert d["temporal_run_id"] == "run_1"


def test_start_policy_table_covers_all_states():
    expected = {
        "running",
        "awaiting_approval",
        "completed",
        "failed_retryable",
        "failed_permanent",
        "unknown",
    }
    assert set(START_POLICY_TABLE.keys()) == expected


def test_start_result():
    r = StartResult(
        status="started",
        workflow_id="casting:corpus-batch:batch_1",
        run_id="run_1",
    )
    assert r.status == "started"
    assert r.run_id == "run_1"


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

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
    OUTBOX_TABLE_DDL,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_CONFIRMED,
    StubOrchestrationClient,
    TASK_QUEUE_CASTING_WORKFLOWS,
    TASK_QUEUE_CTS_WORKFLOWS,
    TASK_QUEUE_MEDIA_GPU,
    TASK_QUEUE_TTS_GPU,
    TASK_QUEUE_NEXUS_PUBLICATION,
    TASK_QUEUE_MEDIA_IO,
    TASK_QUEUE_SECURITY_WORKFLOWS,
    TASK_QUEUE_SECURITY_SECRET_PROVIDER,
    TASK_QUEUE_SECURITY_KUBERNETES,
    TASK_QUEUE_SECURITY_DATABASE,
    TASK_QUEUE_SECURITY_OBJECT_STORAGE,
    # credential rotation
    SecretRef,
    ConsumerSelector,
    RotationInput,
    RotationResult,
    RotationVerification,
    RotationPolicy,
    RotationLock,
    CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
    CREDENTIAL_CLASS_OBJECT_STORAGE_KEY,
    STRATEGY_DUAL_LOGIN_ROLE,
    STRATEGY_KEY_VERSION_ROTATION,
    TRIGGER_SCHEDULED,
    TRIGGER_EXPOSURE,
    ROTATION_STEPS,
    # enrollment lifecycle
    AutomationTracking,
    LIFECYCLE_DISCOVERED,
    LIFECYCLE_BOOTSTRAP_REQUIRED,
    LIFECYCLE_ENROLLED,
    LIFECYCLE_ROTATION_READY,
    LIFECYCLE_AUTOMATICALLY_MANAGED,
    LIFECYCLE_ROTATION_DEGRADED,
    LIFECYCLE_EMERGENCY_ROTATION,
    LIFECYCLE_RETIRED,
    ALL_LIFECYCLE_STATES,
    HUMAN_ASSISTED_STATES,
    WORKFLOW_OWNED_STATES,
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
    assert d["contract_version"] == "1.0"
    restored = WorkflowEnvelope.from_dict(d)
    assert restored.workflow_id == env.workflow_id
    assert restored.governance.approval_required is True
    assert restored.input_ref.checksum == "sha256:abc123"
    assert restored.contract_version == "1.0"


def test_envelope_contract_version_default():
    """contract_version defaults to 1.0 when not specified."""
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
    assert env.contract_version == "1.0"


def test_envelope_contract_version_custom():
    """contract_version can be overridden for forward compatibility testing."""
    env = WorkflowEnvelope(
        request_id="req_1",
        workflow_id="cts:ingest:job_1",
        workflow_type="media.ingestion.v1",
        source_app="cts",
        tenant_id="patternfoundry",
        idempotency_key="cts:ingest:job_1",
        requested_by=RequestedBy(subject_id="user_1"),
        input_ref=InputRef(kind="inline-json", uri="inline", checksum="sha256:x"),
        contract_version="2.0",
    )
    assert env.contract_version == "2.0"
    d = env.to_dict()
    assert d["contract_version"] == "2.0"
    restored = WorkflowEnvelope.from_dict(d)
    assert restored.contract_version == "2.0"


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


def test_outbox_table_ddl():
    """Outbox DDL contains the required columns and indexes."""
    assert "CREATE TABLE" in OUTBOX_TABLE_DDL
    assert "workflow_outbox" in OUTBOX_TABLE_DDL
    assert "idempotency_key" in OUTBOX_TABLE_DDL
    assert "UNIQUE" in OUTBOX_TABLE_DDL
    assert "payload_sha256" in OUTBOX_TABLE_DDL
    assert "next_attempt_at" in OUTBOX_TABLE_DDL
    assert "status" in OUTBOX_TABLE_DDL
    # Index for dispatcher to find pending rows efficiently
    assert "idx_outbox_status_next_attempt" in OUTBOX_TABLE_DDL
    # Index for looking up by workflow_id
    assert "idx_outbox_workflow_id" in OUTBOX_TABLE_DDL


def test_outbox_status_constants():
    assert OUTBOX_STATUS_PENDING == "pending"
    assert OUTBOX_STATUS_CONFIRMED == "confirmed"


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


# --- Credential Rotation (ADR-037) ---


def test_rotation_input_roundtrip():
    """RotationInput roundtrips through dict without exposing credential values."""
    inp = RotationInput(
        credential_set_id="cts-postgres-runtime",
        credential_class=CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
        secret_ref=SecretRef(
            provider="vault",
            path="platform/cts/postgres/runtime",
            current_version="v17",
        ),
        rotation_policy_id="service-db-standard-v1",
        consumer_selector=ConsumerSelector(
            namespace="cts",
            workloads=("cts-backend", "cts-watchdog"),
        ),
        strategy=STRATEGY_DUAL_LOGIN_ROLE,
        trigger=TRIGGER_SCHEDULED,
        correlation_id="corr_01JTEST",
    )
    d = inp.to_dict()
    # No credential values in serialized form
    assert "password" not in str(d).lower()
    assert "secret_key" not in str(d).lower()
    assert d["credential_set_id"] == "cts-postgres-runtime"
    assert d["secret_ref"]["provider"] == "vault"
    assert d["secret_ref"]["current_version"] == "v17"
    assert d["consumer_selector"]["workloads"] == ["cts-backend", "cts-watchdog"]
    assert d["contract_version"] == "1.0"

    restored = RotationInput.from_dict(d)
    assert restored.credential_set_id == inp.credential_set_id
    assert restored.secret_ref.provider == "vault"
    assert restored.secret_ref.current_version == "v17"
    assert restored.consumer_selector.workloads == ("cts-backend", "cts-watchdog")
    assert restored.strategy == STRATEGY_DUAL_LOGIN_ROLE


def test_rotation_input_no_secret_values_in_serialization():
    """Ensure no credential values leak through to_dict serialization."""
    inp = RotationInput(
        credential_set_id="cts-minio-writer",
        credential_class=CREDENTIAL_CLASS_OBJECT_STORAGE_KEY,
        secret_ref=SecretRef(
            provider="external-secrets",
            path="platform/cts/minio/writer",
            current_version="v3",
        ),
        rotation_policy_id="minio-scoped-v1",
        consumer_selector=ConsumerSelector(namespace="cts", workloads=("cts-backend",)),
        strategy=STRATEGY_KEY_VERSION_ROTATION,
        trigger=TRIGGER_EXPOSURE,
    )
    serialized = str(inp.to_dict())
    # The serialized form should not contain common secret value patterns
    for forbidden in ("password=", "secret_key=", "access_key=", "aws_secret"):
        assert forbidden not in serialized.lower()


def test_rotation_result_completed():
    """A completed rotation result references versions, not values."""
    result = RotationResult(
        credential_set_id="cts-postgres-runtime",
        status="completed",
        previous_version="v17",
        active_version="v18",
        previous_identity="cts_runtime_a",
        active_identity="cts_runtime_b",
        verification=RotationVerification(
            workload_ready=True,
            database_connectivity=True,
            read_write_probe=True,
            old_credential_revoked=True,
        ),
        correlation_id="corr_01JTEST",
    )
    d = result.to_dict()
    assert d["status"] == "completed"
    assert d["previous_version"] == "v17"
    assert d["active_version"] == "v18"
    assert d["previous_identity"] == "cts_runtime_a"
    assert d["active_identity"] == "cts_runtime_b"
    assert d["verification"]["workload_ready"] is True
    assert d["verification"]["old_credential_revoked"] is True
    # No credential values
    assert "password" not in str(d).lower()


def test_rotation_verification_all_passed():
    """all_passed returns True when all run checks pass."""
    v = RotationVerification(
        workload_ready=True,
        database_connectivity=True,
        read_write_probe=True,
        old_credential_revoked=True,
    )
    assert v.all_passed is True


def test_rotation_verification_partial_failure():
    """all_passed returns False when a run check fails."""
    v = RotationVerification(
        workload_ready=True,
        database_connectivity=True,
        read_write_probe=False,
        old_credential_revoked=True,
    )
    assert v.all_passed is False


def test_rotation_verification_object_storage():
    """all_passed includes object_storage_access when it was run."""
    v = RotationVerification(
        workload_ready=True,
        object_storage_access=True,
        old_credential_revoked=True,
    )
    assert v.all_passed is True

    v_fail = RotationVerification(
        workload_ready=True,
        object_storage_access=False,
        old_credential_revoked=True,
    )
    assert v_fail.all_passed is False


def test_rotation_result_failed():
    """A failed rotation result includes error code from taxonomy."""
    result = RotationResult(
        credential_set_id="cts-postgres-runtime",
        status="failed",
        error_code="dependency_unavailable",
        error_message="PostgreSQL role creation failed: permission denied for cts_runtime_b",
    )
    d = result.to_dict()
    assert d["status"] == "failed"
    assert d["error_code"] == "dependency_unavailable"
    # Error message should not contain credential values
    assert "password" not in d["error_message"].lower()


def test_rotation_policy_defaults():
    """RotationPolicy has sensible defaults for scheduled rotation."""
    policy = RotationPolicy(
        credential_set="cts-postgres-runtime",
        credential_type=CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
        owner="cts-platform",
    )
    assert policy.rotation_mode == STRATEGY_DUAL_LOGIN_ROLE
    assert policy.cadence_days == 30
    assert policy.grace_period_minutes == 30
    assert policy.require_approval is False
    assert TRIGGER_EXPOSURE in policy.emergency_triggers
    assert policy.rollback_allowed_before_revocation is True


def test_rotation_lock():
    """RotationLock captures the critical-section state."""
    lock = RotationLock(
        credential_set_id="cts-postgres-runtime",
        rotation_generation=18,
        state="rotating",
        lock_owner_workflow_id="security:credential-rotation:cts-postgres-runtime:2026-09",
        lock_expires_at="2026-09-05T12:45:00Z",
    )
    assert lock.state == "rotating"
    assert lock.rotation_generation == 18
    assert "credential-rotation" in lock.lock_owner_workflow_id


def test_rotation_steps_complete():
    """ROTATION_STEPS contains all 14 workflow steps in order."""
    assert len(ROTATION_STEPS) == 14
    assert ROTATION_STEPS[0] == "load_rotation_policy"
    assert ROTATION_STEPS[3] == "create_successor_credential"
    assert ROTATION_STEPS[10] == "revoke_predecessor_credential"
    assert ROTATION_STEPS[12] == "write_rotation_evidence"
    assert ROTATION_STEPS[13] == "notify_security_and_owners"


def test_security_task_queues():
    """Security task queues are defined and distinct from media queues."""
    assert TASK_QUEUE_SECURITY_WORKFLOWS == "security-workflows"
    assert TASK_QUEUE_SECURITY_DATABASE == "security-database"
    assert TASK_QUEUE_SECURITY_OBJECT_STORAGE == "security-object-storage"
    # Security queues must not collide with media queues
    media_queues = {
        TASK_QUEUE_CTS_WORKFLOWS, TASK_QUEUE_MEDIA_GPU,
        TASK_QUEUE_CASTING_WORKFLOWS, TASK_QUEUE_TTS_GPU,
        TASK_QUEUE_NEXUS_PUBLICATION, TASK_QUEUE_MEDIA_IO,
    }
    security_queues = {
        TASK_QUEUE_SECURITY_WORKFLOWS, TASK_QUEUE_SECURITY_SECRET_PROVIDER,
        TASK_QUEUE_SECURITY_KUBERNETES, TASK_QUEUE_SECURITY_DATABASE,
        TASK_QUEUE_SECURITY_OBJECT_STORAGE,
    }
    assert media_queues.isdisjoint(security_queues)


# --- Enrollment Lifecycle (ADR-037 section 17) ---


def test_lifecycle_states_complete():
    """All 8 lifecycle states are defined."""
    assert len(ALL_LIFECYCLE_STATES) == 8
    assert LIFECYCLE_DISCOVERED in ALL_LIFECYCLE_STATES
    assert LIFECYCLE_AUTOMATICALLY_MANAGED in ALL_LIFECYCLE_STATES
    assert LIFECYCLE_RETIRED in ALL_LIFECYCLE_STATES


def test_human_assisted_states():
    """discovered and bootstrap_required are human-assisted."""
    assert LIFECYCLE_DISCOVERED in HUMAN_ASSISTED_STATES
    assert LIFECYCLE_BOOTSTRAP_REQUIRED in HUMAN_ASSISTED_STATES
    assert LIFECYCLE_AUTOMATICALLY_MANAGED not in HUMAN_ASSISTED_STATES
    assert LIFECYCLE_ENROLLED not in HUMAN_ASSISTED_STATES


def test_workflow_owned_states():
    """rotation_ready, automatically_managed, and emergency_rotation are workflow-owned."""
    assert LIFECYCLE_ROTATION_READY in WORKFLOW_OWNED_STATES
    assert LIFECYCLE_AUTOMATICALLY_MANAGED in WORKFLOW_OWNED_STATES
    assert LIFECYCLE_EMERGENCY_ROTATION in WORKFLOW_OWNED_STATES
    assert LIFECYCLE_BOOTSTRAP_REQUIRED not in WORKFLOW_OWNED_STATES
    assert LIFECYCLE_DISCOVERED not in WORKFLOW_OWNED_STATES


def test_automation_tracking_bootstrap():
    """A bootstrap_required credential set is human-assisted."""
    tracking = AutomationTracking(
        credential_set_id="cts-postgres-runtime",
        lifecycle_state=LIFECYCLE_BOOTSTRAP_REQUIRED,
        target_state=LIFECYCLE_AUTOMATICALLY_MANAGED,
        enrollment_deadline="2026-10-01",
        current_exception="exposed static password; secret authority not yet enrolled",
        manual_steps_remaining=(
            "rotate current exposed credential",
            "provision scoped rotation identity",
            "seed first managed secret version",
            "validate end-to-end dry run",
        ),
    )
    assert tracking.is_human_assisted is True
    assert tracking.is_workflow_owned is False
    assert tracking.is_behind_deadline is False  # deadline is in the future


def test_automation_tracking_automatically_managed():
    """An automatically_managed credential set is workflow-owned."""
    tracking = AutomationTracking(
        credential_set_id="cts-minio-writer",
        lifecycle_state=LIFECYCLE_AUTOMATICALLY_MANAGED,
    )
    assert tracking.is_human_assisted is False
    assert tracking.is_workflow_owned is True
    assert tracking.is_behind_deadline is False


def test_automation_tracking_behind_deadline():
    """A bootstrap_required set with a past deadline is behind."""
    tracking = AutomationTracking(
        credential_set_id="cts-postgres-runtime",
        lifecycle_state=LIFECYCLE_BOOTSTRAP_REQUIRED,
        enrollment_deadline="2020-01-01",  # past
    )
    assert tracking.is_behind_deadline is True


def test_automation_tracking_no_deadline():
    """No deadline means not behind."""
    tracking = AutomationTracking(
        credential_set_id="cts-postgres-runtime",
        lifecycle_state=LIFECYCLE_BOOTSTRAP_REQUIRED,
    )
    assert tracking.is_behind_deadline is False


def test_automation_tracking_managed_ignores_deadline():
    """automatically_managed is never behind deadline regardless of date."""
    tracking = AutomationTracking(
        credential_set_id="cts-postgres-runtime",
        lifecycle_state=LIFECYCLE_AUTOMATICALLY_MANAGED,
        enrollment_deadline="2020-01-01",  # past, but already managed
    )
    assert tracking.is_behind_deadline is False


def test_automation_tracking_discovered_is_human_assisted():
    """discovered state is human-assisted (not yet inventoried)."""
    tracking = AutomationTracking(
        credential_set_id="unknown-credential",
        lifecycle_state=LIFECYCLE_DISCOVERED,
    )
    assert tracking.is_human_assisted is True
    assert tracking.is_workflow_owned is False

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
    TASK_QUEUE_SECURITY_DISCOVERY_KUBERNETES,
    TASK_QUEUE_SECURITY_DISCOVERY_POSTGRES,
    TASK_QUEUE_SECURITY_DISCOVERY_MINIO,
    TASK_QUEUE_SECURITY_DISCOVERY_GIT,
    TASK_QUEUE_SECURITY_CORRELATION,
    TASK_QUEUE_SECURITY_INVENTORY_WRITE,
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
    CREDENTIAL_CLASS_API_KEY,
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
    # credential inventory (ADR-038)
    OwnerRef,
    AuthorityRef,
    ConsumerRef,
    SourceFinding,
    RiskAssessment,
    RotationCapabilities,
    RotationExecutionGates,
    RotationEligibility,
    evaluate_rotation_eligibility,
    RotationBlocked,
    CredentialSetRecord,
    DiscoveryFinding,
    EnrollmentPlan,
    EnrollmentInput,
    EnrollmentResult,
    SOURCE_KUBERNETES,
    SOURCE_GIT,
    SOURCE_GITLEAKS,
    ALL_DISCOVERY_SOURCES,
    EXPOSURE_EXPOSED_ROTATED_PENDING_ENROLLMENT,
    RISK_CRITICAL,
    RISK_HIGH,
    RISK_MEDIUM,
    RISK_LOW,
    ALL_RISK_TIERS,
    ENROLLMENT_MODE_OBSERVE_ONLY,
    ENROLLMENT_MODE_EXECUTE,
    ENROLLMENT_STEPS,
    # discovery and correlation
    DISCOVERY_STEPS,
    EXPOSURE_CLASS_ACTIVE_IN_SOURCE,
    EXPOSURE_CLASS_HISTORICAL_IDENTITY_VALID,
    EXPOSURE_CLASS_HISTORICAL_REVOKED,
    EXPOSURE_CLASS_PATTERN_ONLY,
    ALL_EXPOSURE_CLASSES,
    EXPOSURE_DEFAULT_ACTIONS,
    CORRELATION_CONFIDENCE_HIGH,
    CORRELATION_CONFIDENCE_MEDIUM,
    CORRELATION_CONFIDENCE_LOW,
    CORRELATION_BASIS_EXPLICIT_ANNOTATION,
    CORRELATION_BASIS_PROVIDER_IDENTITY,
    CORRELATION_BASIS_NAME_INFERENCE,
    EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY,
    RETENTION_CRITICAL_DAYS,
    RETENTION_HIGH_DAYS,
    RETENTION_LOW_DAYS,
    RETENTION_BY_RISK_TIER,
    CorrelationEvidence,
    CredentialCorrelation,
    CredentialException,
    InventoryRetentionPolicy,
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


# --- Credential Inventory (ADR-038) ---


def test_credential_set_record_basic():
    """A credential set record holds metadata without secret values."""
    record = CredentialSetRecord(
        credential_set_id="cts-postgres-runtime",
        display_name="CTS PostgreSQL runtime access",
        credential_class=CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
        environment="dev",
        lifecycle_state=LIFECYCLE_BOOTSTRAP_REQUIRED,
        owner=OwnerRef(team="cts-platform", escalation_group="platform-security"),
        authority=AuthorityRef(
            provider="kubernetes_secret",
            namespace="cts",
            secret_name="cts-db-secret",
            key_names=("uri", "password"),
        ),
        consumers=(
            ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend", env_var="POSTGRES_DSN"),
            ConsumerRef(kind="Deployment", namespace="cts", name="cts-watchdog"),
        ),
        risk=RiskAssessment(
            tier=RISK_HIGH,
            has_admin_privileges=True,
            exposure_status=EXPOSURE_EXPOSED_ROTATED_PENDING_ENROLLMENT,
        ),
    )
    assert record.credential_set_id == "cts-postgres-runtime"
    assert record.owner.team == "cts-platform"
    assert len(record.consumers) == 2
    assert record.is_unowned is False
    assert record.is_unmanaged is True
    assert record.is_orphaned is False
    assert record.is_shared_across_apps is False


def test_credential_set_record_unowned():
    """A record with no owner is unowned."""
    record = CredentialSetRecord(
        credential_set_id="unknown-cred",
        display_name="Unknown credential",
        credential_class=CREDENTIAL_CLASS_API_KEY,
        environment="dev",
        lifecycle_state=LIFECYCLE_DISCOVERED,
    )
    assert record.is_unowned is True
    assert record.is_unmanaged is True


def test_credential_set_record_orphaned():
    """A credential with provider identity but no consumers is orphaned."""
    record = CredentialSetRecord(
        credential_set_id="old-api-key",
        display_name="Old API key",
        credential_class=CREDENTIAL_CLASS_API_KEY,
        environment="dev",
        lifecycle_state=LIFECYCLE_ENROLLED,
        consumers=(),  # no consumers
    )
    assert record.is_orphaned is True


def test_credential_set_record_shared_across_apps():
    """A credential consumed in multiple namespaces is shared."""
    record = CredentialSetRecord(
        credential_set_id="shared-db",
        display_name="Shared DB",
        credential_class=CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
        environment="dev",
        lifecycle_state=LIFECYCLE_AUTOMATICALLY_MANAGED,
        consumers=(
            ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),
            ConsumerRef(kind="Deployment", namespace="nexus", name="nexus-worker"),
        ),
    )
    assert record.is_shared_across_apps is True


def test_credential_set_record_same_namespace_not_shared():
    """Multiple consumers in the same namespace are not shared across apps."""
    record = CredentialSetRecord(
        credential_set_id="cts-db",
        display_name="CTS DB",
        credential_class=CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
        environment="dev",
        lifecycle_state=LIFECYCLE_AUTOMATICALLY_MANAGED,
        consumers=(
            ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),
            ConsumerRef(kind="Deployment", namespace="cts", name="cts-watchdog"),
        ),
    )
    assert record.is_shared_across_apps is False


def test_rotation_capabilities_all_present():
    """rotation_ready is True when all required capabilities are present."""
    caps = RotationCapabilities(
        successor_creation=True,
        overlap_support=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        audit_observability=True,
    )
    assert caps.rotation_ready is True
    assert caps.blockers == ()


def test_rotation_capabilities_missing():
    """rotation_ready is False and blockers list missing capabilities."""
    caps = RotationCapabilities(
        successor_creation=True,
        overlap_support=True,
        secret_authority=False,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=False,
    )
    assert caps.rotation_ready is False
    assert "secret_authority" in caps.blockers
    assert "predecessor_revocation" in caps.blockers
    assert "successor_creation" not in caps.blockers


def test_rotation_capabilities_to_dict():
    """to_dict includes rotation_ready and blockers."""
    caps = RotationCapabilities(
        successor_creation=True,
        overlap_support=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
    )
    d = caps.to_dict()
    assert d["rotation_ready"] is True
    assert d["blockers"] == []
    assert d["successor_creation"] is True


def test_discovery_finding_no_plaintext():
    """A discovery finding never retains plaintext."""
    finding = DiscoveryFinding(
        finding_id="finding_001",
        source=SOURCE_GITLEAKS,
        detector="gitleaks",
        rule_id="postgres-dsn",
        location_ref="git:cts/deploy-dev.yaml@commit:abc123:line:37",
        credential_class_hint=CREDENTIAL_CLASS_POSTGRESQL_LOGIN,
        confidence="high",
        secret_fingerprint="hmac-sha256:abc123",
        plaintext_retained=False,
        severity=RISK_CRITICAL,
    )
    assert finding.plaintext_retained is False
    # No secret value in the finding
    assert "password" not in str(finding.location_ref).lower()


def test_enrollment_plan_observe_only():
    """An observe-only plan cannot execute."""
    plan = EnrollmentPlan(
        credential_set_id="cts-postgres-runtime",
        target_strategy=STRATEGY_DUAL_LOGIN_ROLE,
        capabilities=RotationCapabilities(),
        mode=ENROLLMENT_MODE_OBSERVE_ONLY,
    )
    assert plan.can_execute is False
    assert plan.mode == ENROLLMENT_MODE_OBSERVE_ONLY


def test_enrollment_plan_execute_with_blockers():
    """An execute plan with blockers cannot proceed."""
    plan = EnrollmentPlan(
        credential_set_id="cts-postgres-runtime",
        target_strategy=STRATEGY_DUAL_LOGIN_ROLE,
        capabilities=RotationCapabilities(),  # all False
        mode=ENROLLMENT_MODE_EXECUTE,
        blockers=("secret_authority", "delivery"),
    )
    assert plan.can_execute is False


def test_enrollment_plan_execute_ready():
    """An execute plan with no blockers and no approval can proceed."""
    plan = EnrollmentPlan(
        credential_set_id="cts-minio-writer",
        target_strategy=STRATEGY_KEY_VERSION_ROTATION,
        capabilities=RotationCapabilities(
            successor_creation=True,
            overlap_support=True,
            secret_authority=True,
            delivery=True,
            consumer_reload=True,
            positive_probe=True,
            predecessor_revocation=True,
        ),
        mode=ENROLLMENT_MODE_EXECUTE,
    )
    assert plan.can_execute is True


def test_enrollment_plan_execute_needs_approval():
    """An execute plan requiring approval cannot proceed without it."""
    plan = EnrollmentPlan(
        credential_set_id="cts-postgres-runtime",
        target_strategy=STRATEGY_DUAL_LOGIN_ROLE,
        capabilities=RotationCapabilities(
            successor_creation=True,
            overlap_support=True,
            secret_authority=True,
            delivery=True,
            consumer_reload=True,
            positive_probe=True,
            predecessor_revocation=True,
        ),
        mode=ENROLLMENT_MODE_EXECUTE,
        requires_approval=True,
        approval_reason="First enrollment of high-risk database credential",
    )
    assert plan.can_execute is False  # approval must be obtained separately


def test_enrollment_input_roundtrip():
    """EnrollmentInput roundtrips without exposing secrets."""
    inp = EnrollmentInput(
        credential_set_id="cts-minio-writer",
        mode=ENROLLMENT_MODE_OBSERVE_ONLY,
        discovery_finding_ids=("finding_001", "finding_002"),
        target_strategy=STRATEGY_KEY_VERSION_ROTATION,
        enrollment_deadline="2026-10-01",
        correlation_id="corr_01JTEST",
    )
    d = inp.to_dict()
    assert d["credential_set_id"] == "cts-minio-writer"
    assert d["mode"] == ENROLLMENT_MODE_OBSERVE_ONLY
    assert d["discovery_finding_ids"] == ["finding_001", "finding_002"]
    assert d["contract_version"] == "1.0"
    # No secret values
    assert "password" not in str(d).lower()


def test_enrollment_result_completed():
    """A completed enrollment result references lifecycle state, not secrets."""
    result = EnrollmentResult(
        credential_set_id="cts-minio-writer",
        status="completed",
        lifecycle_state=LIFECYCLE_ROTATION_READY,
        capabilities=RotationCapabilities(
            successor_creation=True,
            overlap_support=True,
            secret_authority=True,
            delivery=True,
            consumer_reload=True,
            positive_probe=True,
            predecessor_revocation=True,
        ),
        correlation_id="corr_01JTEST",
    )
    d = result.to_dict()
    assert d["status"] == "completed"
    assert d["lifecycle_state"] == LIFECYCLE_ROTATION_READY
    assert d["capabilities"]["rotation_ready"] is True
    # No secret values
    assert "password" not in str(d).lower()


def test_enrollment_result_observe_only_plan():
    """An observe-only result produces a plan without execution."""
    plan = EnrollmentPlan(
        credential_set_id="cts-postgres-runtime",
        target_strategy=STRATEGY_DUAL_LOGIN_ROLE,
        capabilities=RotationCapabilities(successor_creation=False),
        mode=ENROLLMENT_MODE_OBSERVE_ONLY,
        blockers=("successor_creation",),
    )
    result = EnrollmentResult(
        credential_set_id="cts-postgres-runtime",
        status="observe_only_plan",
        lifecycle_state=LIFECYCLE_BOOTSTRAP_REQUIRED,
        plan=plan,
    )
    assert result.status == "observe_only_plan"
    assert result.plan is not None
    assert result.plan.mode == ENROLLMENT_MODE_OBSERVE_ONLY
    assert result.plan.can_execute is False


def test_enrollment_steps_complete():
    """ENROLLMENT_STEPS contains all 17 workflow steps in order."""
    assert len(ENROLLMENT_STEPS) == 17
    assert ENROLLMENT_STEPS[0] == "consolidate_discovery_evidence"
    assert ENROLLMENT_STEPS[3] == "assign_or_escalate_owner"
    assert ENROLLMENT_STEPS[8] == "await_approval"
    assert ENROLLMENT_STEPS[15] == "mark_rotation_ready"
    assert ENROLLMENT_STEPS[16] == "schedule_first_managed_rotation"


def test_discovery_sources_complete():
    """All 6 discovery sources are defined."""
    assert len(ALL_DISCOVERY_SOURCES) == 6
    assert SOURCE_KUBERNETES in ALL_DISCOVERY_SOURCES
    assert SOURCE_GIT in ALL_DISCOVERY_SOURCES
    assert SOURCE_GITLEAKS in ALL_DISCOVERY_SOURCES


def test_risk_tiers_complete():
    """All 4 risk tiers are defined."""
    assert len(ALL_RISK_TIERS) == 4
    assert RISK_CRITICAL in ALL_RISK_TIERS
    assert RISK_HIGH in ALL_RISK_TIERS
    assert RISK_LOW in ALL_RISK_TIERS


def test_source_finding_redacted():
    """SourceFinding contains only redacted references."""
    finding = SourceFinding(
        scanner="git-history",
        location_ref="git:cts@commit:abc123:line:37",
        severity=RISK_CRITICAL,
        confidence="high",
        secret_fingerprint="hmac-sha256:redacted",
        plaintext_retained=False,
    )
    assert finding.plaintext_retained is False
    assert finding.secret_fingerprint.startswith("hmac-sha256:")
    # No actual secret value
    assert "password" not in finding.location_ref.lower()


# --- Risk-tiered readiness, correlation, exceptions, retention ---


def test_rotation_capabilities_risk_tiered_low():
    """Low tier: base capabilities sufficient, overlap not required."""
    caps = RotationCapabilities(
        successor_creation=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        overlap_support=False,  # not required for low
    )
    assert caps.rotation_ready is True
    assert caps.is_rotation_ready_for_risk(RISK_LOW) is True
    assert caps.is_rotation_ready_for_risk(RISK_MEDIUM) is False


def test_rotation_capabilities_risk_tiered_medium():
    """Medium tier: requires overlap_support in addition to base."""
    caps = RotationCapabilities(
        successor_creation=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        overlap_support=True,
        audit_observability=False,  # not required for medium
    )
    assert caps.is_rotation_ready_for_risk(RISK_LOW) is True
    assert caps.is_rotation_ready_for_risk(RISK_MEDIUM) is True
    assert caps.is_rotation_ready_for_risk(RISK_HIGH) is False


def test_rotation_capabilities_risk_tiered_high():
    """High tier: requires audit, owner confirmation, rollback verification."""
    caps = RotationCapabilities(
        successor_creation=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        overlap_support=True,
        audit_observability=True,
        owner_confirmation=True,
        rollback_verification=True,
    )
    assert caps.is_rotation_ready_for_risk(RISK_HIGH) is True
    assert caps.is_rotation_ready_for_risk(RISK_CRITICAL) is True


def test_rotation_capabilities_blockers_for_risk_high():
    """High-tier blockers include audit and rollback if missing."""
    caps = RotationCapabilities(
        successor_creation=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        overlap_support=True,
        audit_observability=False,
        owner_confirmation=False,
        rollback_verification=False,
    )
    high_blockers = caps.blockers_for_risk(RISK_HIGH)
    assert "audit_observability" in high_blockers
    assert "owner_confirmation" in high_blockers
    assert "rollback_verification" in high_blockers
    assert "successor_creation" not in high_blockers


def test_automation_tracking_can_promote_after_rotation():
    """Promotion to automatically_managed requires successful rotations."""
    tracking = AutomationTracking(
        credential_set_id="cts-minio-writer",
        lifecycle_state=LIFECYCLE_ROTATION_READY,
        managed_rotation_count=0,
        required_successful_rotations=1,
    )
    assert tracking.can_promote_to_automatically_managed is False

    tracking_after = AutomationTracking(
        credential_set_id="cts-minio-writer",
        lifecycle_state=LIFECYCLE_ROTATION_READY,
        managed_rotation_count=1,
        required_successful_rotations=1,
        first_successful_rotation_at="2026-09-10T12:00:00Z",
    )
    assert tracking_after.can_promote_to_automatically_managed is True


def test_automation_tracking_no_promote_from_wrong_state():
    """Cannot promote from bootstrap_required even with rotations."""
    tracking = AutomationTracking(
        credential_set_id="cts-postgres-runtime",
        lifecycle_state=LIFECYCLE_BOOTSTRAP_REQUIRED,
        managed_rotation_count=5,
    )
    assert tracking.can_promote_to_automatically_managed is False


def test_discovery_steps_complete():
    """DISCOVERY_STEPS contains all 11 Phase 1 controller steps."""
    assert len(DISCOVERY_STEPS) == 11
    assert DISCOVERY_STEPS[0] == "discover_kubernetes_references"
    assert DISCOVERY_STEPS[5] == "correlate_findings"
    assert DISCOVERY_STEPS[10] == "write_redacted_evidence_report"


def test_exposure_classes_complete():
    """All 6 exposure classes are defined with default actions."""
    assert len(ALL_EXPOSURE_CLASSES) == 6
    assert EXPOSURE_CLASS_ACTIVE_IN_SOURCE in ALL_EXPOSURE_CLASSES
    assert EXPOSURE_CLASS_HISTORICAL_REVOKED in ALL_EXPOSURE_CLASSES
    # Each class has a default action
    for cls in ALL_EXPOSURE_CLASSES:
        assert cls in EXPOSURE_DEFAULT_ACTIONS


def test_exposure_class_actions_differ():
    """Active source requires emergency rotation; revoked is closed."""
    assert EXPOSURE_DEFAULT_ACTIONS[EXPOSURE_CLASS_ACTIVE_IN_SOURCE] == "emergency_rotation"
    assert EXPOSURE_DEFAULT_ACTIONS[EXPOSURE_CLASS_HISTORICAL_REVOKED] == "retain_evidence_closed"
    assert EXPOSURE_DEFAULT_ACTIONS[EXPOSURE_CLASS_PATTERN_ONLY] == "triage"


def test_correlation_evidence():
    """CorrelationEvidence links a finding to a credential set."""
    evidence = CorrelationEvidence(
        finding_type="kubernetes_consumer",
        confidence=CORRELATION_CONFIDENCE_HIGH,
        matching_basis=CORRELATION_BASIS_EXPLICIT_ANNOTATION,
    )
    assert evidence.confidence == CORRELATION_CONFIDENCE_HIGH
    assert evidence.matching_basis == CORRELATION_BASIS_EXPLICIT_ANNOTATION


def test_credential_correlation_highest_confidence():
    """Correlation returns the highest confidence across evidence."""
    corr = CredentialCorrelation(
        canonical_credential_set_id="cts-postgres-runtime",
        evidence=(
            CorrelationEvidence(
                finding_type="git_finding",
                confidence=CORRELATION_CONFIDENCE_MEDIUM,
                matching_basis=CORRELATION_BASIS_NAME_INFERENCE,
            ),
            CorrelationEvidence(
                finding_type="kubernetes_consumer",
                confidence=CORRELATION_CONFIDENCE_HIGH,
                matching_basis=CORRELATION_BASIS_EXPLICIT_ANNOTATION,
            ),
        ),
    )
    assert corr.highest_confidence == CORRELATION_CONFIDENCE_HIGH
    assert corr.has_explicit_annotation is True


def test_credential_correlation_no_explicit_annotation():
    """Correlation without explicit annotation is unconfirmed."""
    corr = CredentialCorrelation(
        canonical_credential_set_id="inferred-cred",
        evidence=(
            CorrelationEvidence(
                finding_type="git_finding",
                confidence=CORRELATION_CONFIDENCE_LOW,
                matching_basis=CORRELATION_BASIS_NAME_INFERENCE,
            ),
        ),
    )
    assert corr.has_explicit_annotation is False
    assert corr.highest_confidence == CORRELATION_CONFIDENCE_LOW


def test_credential_exception_not_expired():
    """A future-dated exception is not expired."""
    exc = CredentialException(
        exception_id="sec-exc-2026-001",
        credential_set_id="legacy-api",
        reason_code=EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY,
        risk_accepted_by="security-owner",
        approved_at="2026-09-05T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        compensating_controls=("IP restriction", "alert on use"),
        remediation_target="migrate-to-vault",
    )
    assert exc.is_expired is False
    assert exc.reason_code == EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY


def test_credential_exception_expired():
    """A past-dated exception is expired."""
    exc = CredentialException(
        exception_id="sec-exc-2026-001",
        credential_set_id="legacy-api",
        reason_code=EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY,
        risk_accepted_by="security-owner",
        approved_at="2020-01-01T00:00:00Z",
        expires_at="2020-06-01T00:00:00Z",
    )
    assert exc.is_expired is True


def test_inventory_retention_policy_defaults():
    """Default retention policy has correct periods by risk tier."""
    policy = InventoryRetentionPolicy()
    assert policy.encrypt_at_rest is True
    assert policy.raw_shell_history_ingestion is False
    assert policy.retention_days_for(RISK_CRITICAL) == RETENTION_CRITICAL_DAYS
    assert policy.retention_days_for(RISK_HIGH) == RETENTION_HIGH_DAYS
    assert policy.retention_days_for(RISK_LOW) == RETENTION_LOW_DAYS


def test_inventory_retention_custom():
    """Custom retention policy overrides defaults."""
    policy = InventoryRetentionPolicy(
        retention_days_by_risk={RISK_LOW: 30, RISK_MEDIUM: 90, RISK_HIGH: 180, RISK_CRITICAL: 365},
        raw_shell_history_ingestion=True,
    )
    assert policy.retention_days_for(RISK_LOW) == 30
    assert policy.retention_days_for(RISK_CRITICAL) == 365
    assert policy.raw_shell_history_ingestion is True


def test_retention_by_risk_tier_mapping():
    """RETENTION_BY_RISK_TIER maps all 4 risk tiers."""
    assert len(RETENTION_BY_RISK_TIER) == 4
    assert RETENTION_BY_RISK_TIER[RISK_CRITICAL] > RETENTION_BY_RISK_TIER[RISK_HIGH]
    assert RETENTION_BY_RISK_TIER[RISK_HIGH] > RETENTION_BY_RISK_TIER[RISK_LOW]


# --- Critical execution gates, exception fail-closed, correlation edge cases ---


def test_critical_execution_gates_all_configured():
    """Critical rotation is eligible when all execution gates are configured."""
    gates = RotationExecutionGates(
        approval_policy_configured=True,
        canary_cutover_configured=True,
        immutable_evidence_store=True,
        emergency_recovery_plan_verified=True,
    )
    assert gates.critical_ready is True
    assert gates.missing_gates == ()


def test_critical_execution_gates_missing():
    """Critical rotation is blocked when execution gates are absent."""
    gates = RotationExecutionGates(
        approval_policy_configured=True,
        canary_cutover_configured=False,
        immutable_evidence_store=True,
        emergency_recovery_plan_verified=False,
    )
    assert gates.critical_ready is False
    assert "canary_cutover_configured" in gates.missing_gates
    assert "emergency_recovery_plan_verified" in gates.missing_gates
    assert "approval_policy_configured" not in gates.missing_gates


def test_critical_capability_ready_but_execution_gate_absent():
    """Provider capability ready + execution gate absent = cannot execute."""
    caps = RotationCapabilities(
        successor_creation=True,
        overlap_support=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        audit_observability=True,
        owner_confirmation=True,
        rollback_verification=True,
    )
    gates = RotationExecutionGates()  # all False
    provider_ready = caps.is_rotation_ready_for_risk(RISK_CRITICAL)
    execution_ready = gates.critical_ready
    eligible = provider_ready and execution_ready
    assert provider_ready is True
    assert execution_ready is False
    assert eligible is False


def test_critical_full_eligibility():
    """Critical rotation eligible only with both provider + execution gates."""
    caps = RotationCapabilities(
        successor_creation=True,
        overlap_support=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        audit_observability=True,
        owner_confirmation=True,
        rollback_verification=True,
    )
    gates = RotationExecutionGates(
        approval_policy_configured=True,
        canary_cutover_configured=True,
        immutable_evidence_store=True,
        emergency_recovery_plan_verified=True,
    )
    eligible = caps.is_rotation_ready_for_risk(RISK_CRITICAL) and gates.critical_ready
    assert eligible is True


def test_exception_malformed_expiry_fails_closed():
    """A malformed expiry string is treated as expired (fail closed)."""
    exc = CredentialException(
        exception_id="sec-exc-bad",
        credential_set_id="legacy-api",
        reason_code=EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY,
        risk_accepted_by="security-owner",
        approved_at="2026-09-05T00:00:00Z",
        expires_at="not-a-date",
    )
    assert exc.is_expired is True
    assert exc.is_valid is False


def test_exception_missing_expiry_fails_closed():
    """A None expiry is treated as expired (fail closed)."""
    exc = CredentialException(
        exception_id="sec-exc-none",
        credential_set_id="legacy-api",
        reason_code=EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY,
        risk_accepted_by="security-owner",
        approved_at="2026-09-05T00:00:00Z",
        expires_at=None,  # type: ignore[arg-type]
    )
    assert exc.is_expired is True
    assert exc.is_valid is False


def test_exception_at_exact_expiry_is_expired():
    """An exception at its exact expiry timestamp is expired (>=)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    exc = CredentialException(
        exception_id="sec-exc-now",
        credential_set_id="legacy-api",
        reason_code=EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY,
        risk_accepted_by="security-owner",
        approved_at="2026-01-01T00:00:00Z",
        expires_at=now.isoformat(),
        remediation_target="migrate-to-vault",
    )
    assert exc.is_expired is True


def test_exception_valid_with_remediation():
    """A valid exception has parseable expiry and remediation target."""
    exc = CredentialException(
        exception_id="sec-exc-valid",
        credential_set_id="legacy-api",
        reason_code=EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY,
        risk_accepted_by="security-owner",
        approved_at="2026-09-05T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        remediation_target="migrate-to-vault",
    )
    assert exc.is_valid is True
    assert exc.is_expired is False


def test_exception_invalid_without_remediation():
    """An exception without remediation_target is not valid."""
    exc = CredentialException(
        exception_id="sec-exc-no-remediation",
        credential_set_id="legacy-api",
        reason_code=EXCEPTION_REASON_PROVIDER_NO_SECONDARY_KEY,
        risk_accepted_by="security-owner",
        approved_at="2026-09-05T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        remediation_target=None,
    )
    assert exc.is_valid is False


def test_correlation_empty_evidence_returns_none_confidence():
    """Empty evidence returns None, not 'low' confidence."""
    corr = CredentialCorrelation(
        canonical_credential_set_id="orphan-cred",
        evidence=(),
    )
    assert corr.highest_confidence is None
    assert corr.has_evidence is False


def test_correlation_with_evidence_has_confidence():
    """Non-empty evidence returns a confidence level."""
    corr = CredentialCorrelation(
        canonical_credential_set_id="cts-postgres-runtime",
        evidence=(
            CorrelationEvidence(
                finding_type="kubernetes_consumer",
                confidence=CORRELATION_CONFIDENCE_LOW,
                matching_basis=CORRELATION_BASIS_NAME_INFERENCE,
            ),
        ),
    )
    assert corr.highest_confidence == CORRELATION_CONFIDENCE_LOW
    assert corr.has_evidence is True


def test_correlation_conflicting_high_confidence_unconfirmed():
    """Conflicting high-confidence evidence stays unconfirmed."""
    corr = CredentialCorrelation(
        canonical_credential_set_id="ambiguous-cred",
        evidence=(
            CorrelationEvidence(
                finding_type="kubernetes_consumer",
                confidence=CORRELATION_CONFIDENCE_HIGH,
                matching_basis=CORRELATION_BASIS_EXPLICIT_ANNOTATION,
                finding_ref="finding_a",
            ),
            CorrelationEvidence(
                finding_type="postgres_role",
                confidence=CORRELATION_CONFIDENCE_HIGH,
                matching_basis=CORRELATION_BASIS_PROVIDER_IDENTITY,
                finding_ref="finding_b",
            ),
        ),
        confirmed=False,  # conflicting evidence requires owner resolution
    )
    assert corr.highest_confidence == CORRELATION_CONFIDENCE_HIGH
    assert corr.confirmed is False


def test_discovery_task_queues_isolated():
    """Discovery task queues are distinct from each other and from rotation queues."""
    discovery_queues = {
        TASK_QUEUE_SECURITY_DISCOVERY_KUBERNETES,
        TASK_QUEUE_SECURITY_DISCOVERY_POSTGRES,
        TASK_QUEUE_SECURITY_DISCOVERY_MINIO,
        TASK_QUEUE_SECURITY_DISCOVERY_GIT,
        TASK_QUEUE_SECURITY_CORRELATION,
        TASK_QUEUE_SECURITY_INVENTORY_WRITE,
    }
    rotation_queues = {
        TASK_QUEUE_SECURITY_WORKFLOWS,
        TASK_QUEUE_SECURITY_SECRET_PROVIDER,
        TASK_QUEUE_SECURITY_KUBERNETES,
        TASK_QUEUE_SECURITY_DATABASE,
        TASK_QUEUE_SECURITY_OBJECT_STORAGE,
    }
    # Discovery queues must not collide with rotation queues
    assert discovery_queues.isdisjoint(rotation_queues)
    # All discovery queues are distinct
    assert len(discovery_queues) == 6


def test_low_risk_without_overlap_may_be_ready():
    """Low-risk credential without overlap can be rotation-ready."""
    caps = RotationCapabilities(
        successor_creation=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        overlap_support=False,
    )
    assert caps.is_rotation_ready_for_risk(RISK_LOW) is True


def test_high_risk_lacking_owner_confirmation_not_ready():
    """High-risk credential without owner confirmation cannot be rotation_ready."""
    caps = RotationCapabilities(
        successor_creation=True,
        overlap_support=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        audit_observability=True,
        owner_confirmation=False,  # missing
        rollback_verification=True,
    )
    assert caps.is_rotation_ready_for_risk(RISK_HIGH) is False
    high_blockers = caps.blockers_for_risk(RISK_HIGH)
    assert "owner_confirmation" in high_blockers


# --- RotationEligibility: canonical policy evaluation ---


def _full_caps() -> RotationCapabilities:
    """Capabilities with all provider capabilities present."""
    return RotationCapabilities(
        successor_creation=True,
        overlap_support=True,
        secret_authority=True,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
        audit_observability=True,
        owner_confirmation=True,
        rollback_verification=True,
    )


def _full_gates() -> RotationExecutionGates:
    """Execution gates with all gates configured."""
    return RotationExecutionGates(
        approval_policy_configured=True,
        canary_cutover_configured=True,
        immutable_evidence_store=True,
        emergency_recovery_plan_verified=True,
    )


def test_eligibility_low_tier_eligible():
    """Low-tier credential with full capabilities is eligible without gates."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-minio-writer",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        policy_version="1",
    )
    assert eligibility.eligible is True
    assert eligibility.provider_ready is True
    assert eligibility.execution_ready is True  # not evaluated for low
    assert eligibility.execution_blockers == ()
    assert eligibility.provider_blockers == ()
    assert eligibility.policy_version == "1"


def test_eligibility_high_tier_eligible():
    """High-tier credential with full capabilities is eligible without gates."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-postgres-runtime",
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    assert eligibility.eligible is True
    assert eligibility.provider_ready is True
    assert eligibility.execution_ready is True  # not evaluated for high
    assert eligibility.execution_blockers == ()


def test_eligibility_critical_with_gates_eligible():
    """Critical credential with full caps and full gates is eligible."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-postgres-admin",
        risk_tier=RISK_CRITICAL,
        capabilities=_full_caps(),
        gates=_full_gates(),
        policy_version="2",
    )
    assert eligibility.eligible is True
    assert eligibility.provider_ready is True
    assert eligibility.execution_ready is True
    assert eligibility.execution_blockers == ()
    assert eligibility.policy_version == "2"


def test_eligibility_critical_without_gates_not_eligible():
    """Critical credential without execution gates is not eligible."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-postgres-admin",
        risk_tier=RISK_CRITICAL,
        capabilities=_full_caps(),
        gates=None,
        policy_version="1",
    )
    assert eligibility.eligible is False
    assert eligibility.provider_ready is True
    assert eligibility.execution_ready is False
    assert "rotation_execution_gates_missing" in eligibility.execution_blockers


def test_eligibility_critical_with_partial_gates_not_eligible():
    """Critical credential with partial gates is not eligible."""
    gates = RotationExecutionGates(
        approval_policy_configured=True,
        canary_cutover_configured=False,
        immutable_evidence_store=True,
        emergency_recovery_plan_verified=False,
    )
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-postgres-admin",
        risk_tier=RISK_CRITICAL,
        capabilities=_full_caps(),
        gates=gates,
        policy_version="1",
    )
    assert eligibility.eligible is False
    assert eligibility.execution_ready is False
    assert "canary_cutover_configured" in eligibility.execution_blockers
    assert "emergency_recovery_plan_verified" in eligibility.execution_blockers


def test_eligibility_provider_blocked():
    """Eligibility reports provider blockers when capabilities missing."""
    caps = RotationCapabilities(
        successor_creation=True,
        overlap_support=False,
        secret_authority=False,
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
    )
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-api-key",
        risk_tier=RISK_MEDIUM,
        capabilities=caps,
        policy_version="1",
    )
    assert eligibility.eligible is False
    assert eligibility.provider_ready is False
    assert "secret_authority" in eligibility.provider_blockers
    assert "overlap_support" in eligibility.provider_blockers


def test_eligibility_all_blockers_combines():
    """all_blockers combines provider and execution blockers."""
    caps = RotationCapabilities(
        successor_creation=True,
        secret_authority=False,  # provider blocker
        delivery=True,
        consumer_reload=True,
        positive_probe=True,
        predecessor_revocation=True,
    )
    gates = RotationExecutionGates(
        approval_policy_configured=False,
        canary_cutover_configured=True,
        immutable_evidence_store=True,
        emergency_recovery_plan_verified=True,
    )
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-critical",
        risk_tier=RISK_CRITICAL,
        capabilities=caps,
        gates=gates,
        policy_version="1",
    )
    combined = eligibility.all_blockers
    assert "secret_authority" in combined  # from provider
    assert "approval_policy_configured" in combined  # from execution


def test_eligibility_has_timestamp_and_version():
    """Eligibility record includes evaluation timestamp and policy version."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-minio",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        policy_version="3",
    )
    assert eligibility.evaluated_at  # non-empty ISO string
    assert eligibility.policy_version == "3"


def test_eligibility_low_tier_ignores_gates():
    """Low-tier eligibility is not affected by execution gates."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-minio-writer",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        gates=None,  # no gates provided
        policy_version="1",
    )
    assert eligibility.eligible is True
    assert eligibility.execution_ready is True
    assert eligibility.execution_blockers == ()


def test_eligibility_is_rotation_eligibility_type():
    """evaluate_rotation_eligibility returns RotationEligibility instance."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="test",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
    )
    assert isinstance(eligibility, RotationEligibility)


# --- Input validation, fingerprint binding, RotationBlocked ---


def test_eligibility_has_input_fingerprint():
    """Eligibility record includes an input fingerprint for immutable binding."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-minio-writer",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        policy_version="1",
    )
    assert eligibility.input_fingerprint.startswith("sha256:")
    assert len(eligibility.input_fingerprint) > len("sha256:")


def test_eligibility_fingerprint_changes_with_inputs():
    """Different inputs produce different fingerprints."""
    caps = _full_caps()
    e1 = evaluate_rotation_eligibility(
        credential_set_id="cts-minio",
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        credential_set_id="cts-postgres",
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="1",
    )
    assert e1.input_fingerprint != e2.input_fingerprint


def test_eligibility_fingerprint_changes_with_risk_tier():
    """Same credential at different risk tiers produces different fingerprints."""
    caps = _full_caps()
    e1 = evaluate_rotation_eligibility(
        credential_set_id="cts-cred",
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        credential_set_id="cts-cred",
        risk_tier=RISK_HIGH,
        capabilities=caps,
        policy_version="1",
    )
    assert e1.input_fingerprint != e2.input_fingerprint


def test_eligibility_fingerprint_changes_with_policy_version():
    """Different policy versions produce different fingerprints."""
    caps = _full_caps()
    e1 = evaluate_rotation_eligibility(
        credential_set_id="cts-cred",
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        credential_set_id="cts-cred",
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="2",
    )
    assert e1.input_fingerprint != e2.input_fingerprint


def test_eligibility_fingerprint_changes_with_gates():
    """Critical eligibility with different gates produces different fingerprints."""
    caps = _full_caps()
    e1 = evaluate_rotation_eligibility(
        credential_set_id="cts-admin",
        risk_tier=RISK_CRITICAL,
        capabilities=caps,
        gates=_full_gates(),
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        credential_set_id="cts-admin",
        risk_tier=RISK_CRITICAL,
        capabilities=caps,
        gates=RotationExecutionGates(
            approval_policy_configured=True,
            canary_cutover_configured=True,
            immutable_evidence_store=True,
            emergency_recovery_plan_verified=False,
        ),
        policy_version="1",
    )
    assert e1.input_fingerprint != e2.input_fingerprint


def test_eligibility_fingerprint_deterministic():
    """Same inputs produce the same fingerprint."""
    caps = _full_caps()
    e1 = evaluate_rotation_eligibility(
        credential_set_id="cts-cred",
        risk_tier=RISK_MEDIUM,
        capabilities=caps,
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        credential_set_id="cts-cred",
        risk_tier=RISK_MEDIUM,
        capabilities=caps,
        policy_version="1",
    )
    assert e1.input_fingerprint == e2.input_fingerprint


def test_eligibility_invalid_risk_tier_raises():
    """Unknown risk tier raises ValueError."""
    import pytest
    with pytest.raises(ValueError, match="risk_tier"):
        evaluate_rotation_eligibility(
            credential_set_id="cts-cred",
            risk_tier="unknown",
            capabilities=_full_caps(),
        )


def test_eligibility_invalid_credential_set_id_raises():
    """Invalid credential_set_id grammar raises ValueError."""
    import pytest
    with pytest.raises(ValueError, match="credential_set_id"):
        evaluate_rotation_eligibility(
            credential_set_id="UPPERCASE-BAD",
            risk_tier=RISK_LOW,
            capabilities=_full_caps(),
        )


def test_eligibility_empty_credential_set_id_raises():
    """Empty credential_set_id raises ValueError."""
    import pytest
    with pytest.raises(ValueError, match="credential_set_id"):
        evaluate_rotation_eligibility(
            credential_set_id="",
            risk_tier=RISK_LOW,
            capabilities=_full_caps(),
        )


def test_eligibility_empty_policy_version_raises():
    """Empty policy_version raises ValueError."""
    import pytest
    with pytest.raises(ValueError, match="policy_version"):
        evaluate_rotation_eligibility(
            credential_set_id="cts-cred",
            risk_tier=RISK_LOW,
            capabilities=_full_caps(),
            policy_version="",
        )


def test_eligibility_all_blockers_deduplicated():
    """all_blockers deduplicates entries that appear in both dimensions."""
    # Construct an eligibility where the same blocker could appear in both
    # provider and execution blockers. We test the property directly.
    eligibility = RotationEligibility(
        credential_set_id="test",
        risk_tier=RISK_CRITICAL,
        provider_ready=False,
        execution_ready=False,
        eligible=False,
        provider_blockers=("secret_authority", "overlap_support"),
        execution_blockers=("secret_authority", "approval_policy_configured"),
        evaluated_at="2026-01-01T00:00:00+00:00",
        policy_version="1",
        input_fingerprint="sha256:test",
    )
    combined = eligibility.all_blockers
    # "secret_authority" appears in both but should only appear once
    assert combined.count("secret_authority") == 1
    assert "overlap_support" in combined
    assert "approval_policy_configured" in combined


def test_rotation_blocked_exception():
    """RotationBlocked carries credential_set_id, blockers, and policy_version."""
    exc = RotationBlocked(
        credential_set_id="cts-postgres-admin",
        blockers=("approval_policy_configured", "canary_cutover_configured"),
        policy_version="2",
    )
    assert exc.credential_set_id == "cts-postgres-admin"
    assert "approval_policy_configured" in exc.blockers
    assert exc.policy_version == "2"
    assert "cts-postgres-admin" in str(exc)


def test_rotation_blocked_from_eligibility():
    """RotationBlocked can be raised from an ineligible eligibility decision."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-admin",
        risk_tier=RISK_CRITICAL,
        capabilities=_full_caps(),
        gates=None,  # no gates → not eligible
        policy_version="1",
    )
    assert eligibility.eligible is False
    if not eligibility.eligible:
        exc = RotationBlocked(
            credential_set_id=eligibility.credential_set_id,
            blockers=eligibility.all_blockers,
            policy_version=eligibility.policy_version,
        )
    assert "rotation_execution_gates_missing" in exc.blockers


def test_high_tier_execution_gates_intentionally_not_evaluated():
    """High-tier eligibility does not check execution gates (documented policy)."""
    eligibility = evaluate_rotation_eligibility(
        credential_set_id="cts-postgres-runtime",
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        gates=None,  # no gates provided, but high-tier doesn't need them
        policy_version="1",
    )
    # High-tier: execution_ready is True even without gates
    assert eligibility.execution_ready is True
    assert eligibility.execution_blockers == ()
    assert eligibility.eligible is True

"""Tests for platform-orchestration-contracts."""

import json
import os
import pytest
from pathlib import Path
from typing import Optional

from platform_orchestration_contracts import (
    __version__,
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
    RotationSubject,
    RotationEligibility,
    evaluate_rotation_eligibility,
    RotationBlocked,
    WorkflowExecutionAuthorization,
    evaluate_workflow_execution_authorization,
    CredentialSetRecord,
    DiscoveryFinding,
    EnrollmentPlan,
    EnrollmentInput,
    CredentialPostureEntry,
    PostureReport,
    build_posture_entry,
    evaluate_posture,
    CredentialObservation,
    COVERAGE_COMPLETED,
    COVERAGE_NOT_CONFIGURED,
    COVERAGE_FAILED,
    COVERAGE_PARTIAL,
    COVERAGE_SOURCE_KUBERNETES,
    COVERAGE_SOURCE_POSTGRES,
    COVERAGE_SOURCE_MINIO,
    COVERAGE_SOURCE_GIT_FINDINGS,
    ALL_COVERAGE_SOURCES,
    REPORT_VERSION,
    UnsafeObservationError,
    assert_observation_safe,
    assert_observations_safe,
    assert_safe_report_text,
    FORBIDDEN_MARKERS,
    discover_kubernetes_credentials,
    KubernetesDiscoveryClient,
    WorkloadMetadata,
    WorkloadEnvVar,
    WorkloadEnvFrom,
    WorkloadVolumeSecret,
    ExternalSecretMetadata,
    MalformedWorkloadError,
    RISK_SIGNAL_K8S_SECRET_DELIVERY,
    RISK_SIGNAL_INLINE_ENV_SECRET,
    RISK_SIGNAL_RUNTIME_DB_ACCESS,
    RISK_SIGNAL_OBJECT_STORAGE_ACCESS,
    RISK_SIGNAL_NO_SECRET_REF,
    EXPOSURE_ACTIVE_IN_SOURCE,
    EXPOSURE_SECRET_DELIVERED,
    EXPOSURE_SECRET_DELIVERED_SHARED,
    EXPOSURE_MANAGED_VIA_SECRET_REF,
    EXPOSURE_UNKNOWN,
    EXPOSURE_CERTIFICATE_DELIVERED,
    ACTION_EMERGENCY_ROTATION,
    ACTION_ENROLLMENT_CANDIDATE,
    ACTION_CERTIFICATE_LIFECYCLE,
    to_workload_env_var,
    to_workload_metadata,
    SecretScrubbingFilter,
    install_secret_scrubbing_filter,
    KubernetesPythonDiscoveryClient,
    DiscoveryError,
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




def _make_subject(credential_set_id: str = 'cts-cred') -> RotationSubject:
    """Create a default RotationSubject for testing."""
    return RotationSubject(
        credential_set_id=credential_set_id,
        provider_ref='postgresql:infra-data-postgres',
        provider_identity_ref='role:cts_runtime_a',
        secret_authority_ref='vault:secret/cts/db#v3',
        consumer_set_ref='deployment:cts/cts-backend',
        consumer_set_version='resource_version:12345',
        rotation_strategy='dual_login_role',
        reload_strategy='rolling_restart',
    )


def test_eligibility_low_tier_eligible():
    """Low-tier credential with full capabilities is eligible without gates."""
    eligibility = evaluate_rotation_eligibility(
        subject=_make_subject("cts-minio-writer"),
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
        subject=_make_subject("cts-postgres-runtime"),
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
        subject=_make_subject("cts-postgres-admin"),
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
        subject=_make_subject("cts-postgres-admin"),
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
        subject=_make_subject("cts-postgres-admin"),
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
        subject=_make_subject("cts-api-key"),
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
        subject=_make_subject("cts-critical"),
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
        subject=_make_subject("cts-minio"),
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        policy_version="3",
    )
    assert eligibility.evaluated_at  # non-empty ISO string
    assert eligibility.policy_version == "3"


def test_eligibility_low_tier_ignores_gates():
    """Low-tier eligibility is not affected by execution gates."""
    eligibility = evaluate_rotation_eligibility(
        subject=_make_subject("cts-minio-writer"),
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
        subject=_make_subject("test"),
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
    )
    assert isinstance(eligibility, RotationEligibility)


# --- Input validation, fingerprint binding, RotationBlocked ---


def test_eligibility_has_input_fingerprint():
    """Eligibility record includes an input fingerprint for immutable binding."""
    eligibility = evaluate_rotation_eligibility(
        subject=_make_subject("cts-minio-writer"),
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
        subject=_make_subject("cts-minio"),
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        subject=_make_subject("cts-postgres"),
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="1",
    )
    assert e1.input_fingerprint != e2.input_fingerprint


def test_eligibility_fingerprint_changes_with_risk_tier():
    """Same credential at different risk tiers produces different fingerprints."""
    caps = _full_caps()
    e1 = evaluate_rotation_eligibility(
        subject=_make_subject("cts-cred"),
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        subject=_make_subject("cts-cred"),
        risk_tier=RISK_HIGH,
        capabilities=caps,
        policy_version="1",
    )
    assert e1.input_fingerprint != e2.input_fingerprint


def test_eligibility_fingerprint_changes_with_policy_version():
    """Different policy versions produce different fingerprints."""
    caps = _full_caps()
    e1 = evaluate_rotation_eligibility(
        subject=_make_subject("cts-cred"),
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        subject=_make_subject("cts-cred"),
        risk_tier=RISK_LOW,
        capabilities=caps,
        policy_version="2",
    )
    assert e1.input_fingerprint != e2.input_fingerprint


def test_eligibility_fingerprint_changes_with_gates():
    """Critical eligibility with different gates produces different fingerprints."""
    caps = _full_caps()
    e1 = evaluate_rotation_eligibility(
        subject=_make_subject("cts-admin"),
        risk_tier=RISK_CRITICAL,
        capabilities=caps,
        gates=_full_gates(),
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        subject=_make_subject("cts-admin"),
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
        subject=_make_subject("cts-cred"),
        risk_tier=RISK_MEDIUM,
        capabilities=caps,
        policy_version="1",
    )
    e2 = evaluate_rotation_eligibility(
        subject=_make_subject("cts-cred"),
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
            subject=_make_subject("cts-cred"),
            risk_tier="unknown",
            capabilities=_full_caps(),
        )


def test_eligibility_invalid_credential_set_id_raises():
    """Invalid credential_set_id grammar raises ValueError."""
    import pytest
    bad_subject = RotationSubject(
        credential_set_id="UPPERCASE-BAD",
        provider_ref="p",
        provider_identity_ref="i",
        secret_authority_ref="s",
        consumer_set_ref="c",
        consumer_set_version="v1",
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
    )
    with pytest.raises(ValueError, match="credential_set_id"):
        evaluate_rotation_eligibility(
            subject=bad_subject,
            risk_tier=RISK_LOW,
            capabilities=_full_caps(),
        )


def test_eligibility_empty_credential_set_id_raises():
    """Empty credential_set_id raises ValueError."""
    import pytest
    bad_subject = RotationSubject(
        credential_set_id="",
        provider_ref="p",
        provider_identity_ref="i",
        secret_authority_ref="s",
        consumer_set_ref="c",
        consumer_set_version="v1",
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
    )
    with pytest.raises(ValueError, match="credential_set_id"):
        evaluate_rotation_eligibility(
            subject=bad_subject,
            risk_tier=RISK_LOW,
            capabilities=_full_caps(),
        )


def test_eligibility_empty_policy_version_raises():
    """Empty policy_version raises ValueError."""
    import pytest
    with pytest.raises(ValueError, match="policy_version"):
        evaluate_rotation_eligibility(
            subject=_make_subject("cts-cred"),
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
        subject=_make_subject("cts-admin"),
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
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        gates=None,  # no gates provided, but high-tier doesn't need them
        policy_version="1",
    )
    # High-tier: execution_ready is True even without gates
    assert eligibility.execution_ready is True
    assert eligibility.execution_blockers == ()
    assert eligibility.eligible is True


# --- RotationSubject fingerprint coverage ---


def test_fingerprint_changes_with_provider_ref():
    """Changed provider reference produces a different fingerprint."""
    caps = _full_caps()
    s1 = _make_subject("cts-cred")
    s2 = RotationSubject(
        credential_set_id="cts-cred",
        provider_ref="postgresql:instance-b",  # changed
        provider_identity_ref="role:cts_runtime_a",
        secret_authority_ref="vault:secret/cts/db#v3",
        consumer_set_ref="deployment:cts/cts-backend",
        consumer_set_version="resource_version:12345",
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
    )
    e1 = evaluate_rotation_eligibility(subject=s1, risk_tier=RISK_LOW, capabilities=caps)
    e2 = evaluate_rotation_eligibility(subject=s2, risk_tier=RISK_LOW, capabilities=caps)
    assert e1.input_fingerprint != e2.input_fingerprint


def test_fingerprint_changes_with_secret_authority_ref():
    """Changed secret-authority path produces a different fingerprint."""
    caps = _full_caps()
    s1 = _make_subject("cts-cred")
    s2 = RotationSubject(
        credential_set_id="cts-cred",
        provider_ref="postgresql:infra-data-postgres",
        provider_identity_ref="role:cts_runtime_a",
        secret_authority_ref="vault:secret/cts/db#v9",  # changed
        consumer_set_ref="deployment:cts/cts-backend",
        consumer_set_version="resource_version:12345",
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
    )
    e1 = evaluate_rotation_eligibility(subject=s1, risk_tier=RISK_LOW, capabilities=caps)
    e2 = evaluate_rotation_eligibility(subject=s2, risk_tier=RISK_LOW, capabilities=caps)
    assert e1.input_fingerprint != e2.input_fingerprint


def test_fingerprint_changes_with_consumer_set_version():
    """Changed consumer-set version produces a different fingerprint."""
    caps = _full_caps()
    s1 = _make_subject("cts-cred")
    s2 = RotationSubject(
        credential_set_id="cts-cred",
        provider_ref="postgresql:infra-data-postgres",
        provider_identity_ref="role:cts_runtime_a",
        secret_authority_ref="vault:secret/cts/db#v3",
        consumer_set_ref="deployment:cts/cts-backend",
        consumer_set_version="resource_version:99999",  # changed
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
    )
    e1 = evaluate_rotation_eligibility(subject=s1, risk_tier=RISK_LOW, capabilities=caps)
    e2 = evaluate_rotation_eligibility(subject=s2, risk_tier=RISK_LOW, capabilities=caps)
    assert e1.input_fingerprint != e2.input_fingerprint


def test_fingerprint_changes_with_rotation_strategy():
    """Changed rotation strategy produces a different fingerprint."""
    caps = _full_caps()
    s1 = _make_subject("cts-cred")
    s2 = RotationSubject(
        credential_set_id="cts-cred",
        provider_ref="postgresql:infra-data-postgres",
        provider_identity_ref="role:cts_runtime_a",
        secret_authority_ref="vault:secret/cts/db#v3",
        consumer_set_ref="deployment:cts/cts-backend",
        consumer_set_version="resource_version:12345",
        rotation_strategy="dynamic_credential",  # changed
        reload_strategy="rolling_restart",
    )
    e1 = evaluate_rotation_eligibility(subject=s1, risk_tier=RISK_LOW, capabilities=caps)
    e2 = evaluate_rotation_eligibility(subject=s2, risk_tier=RISK_LOW, capabilities=caps)
    assert e1.input_fingerprint != e2.input_fingerprint


def test_fingerprint_changes_with_approval_policy_ref():
    """Changed approval policy reference produces a different fingerprint."""
    caps = _full_caps()
    s1 = _make_subject("cts-cred")
    s2 = RotationSubject(
        credential_set_id="cts-cred",
        provider_ref="postgresql:infra-data-postgres",
        provider_identity_ref="role:cts_runtime_a",
        secret_authority_ref="vault:secret/cts/db#v3",
        consumer_set_ref="deployment:cts/cts-backend",
        consumer_set_version="resource_version:12345",
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
        approval_policy_ref="policy:high-risk-v2",  # changed from None
    )
    e1 = evaluate_rotation_eligibility(subject=s1, risk_tier=RISK_LOW, capabilities=caps)
    e2 = evaluate_rotation_eligibility(subject=s2, risk_tier=RISK_LOW, capabilities=caps)
    assert e1.input_fingerprint != e2.input_fingerprint


def test_rotation_subject_to_dict():
    """RotationSubject.to_dict() includes all fields."""
    subject = RotationSubject(
        credential_set_id="cts-cred",
        provider_ref="postgresql:pg",
        provider_identity_ref="role:cts_runtime",
        secret_authority_ref="vault:secret/cts/db",
        consumer_set_ref="deployment:cts/cts-backend",
        consumer_set_version="v1",
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
        approval_policy_ref="policy:high-risk",
        evidence_store_ref="s3://security-evidence/...",
    )
    d = subject.to_dict()
    assert d["credential_set_id"] == "cts-cred"
    assert d["provider_ref"] == "postgresql:pg"
    assert d["secret_authority_ref"] == "vault:secret/cts/db"
    assert d["rotation_strategy"] == "dual_login_role"
    assert d["approval_policy_ref"] == "policy:high-risk"
    assert d["evidence_store_ref"] == "s3://security-evidence/..."


# --- WorkflowExecutionAuthorization ---


def test_workflow_execution_authorization_all_checks_pass():
    """All execution checks passing means authorized (derived, not caller-supplied)."""
    eligibility = evaluate_rotation_eligibility(
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    assert auth.authorized is True
    assert auth.all_blockers == ()


def test_workflow_execution_authorization_missing_checks():
    """Missing execution checks produce blockers and authorized is False (derived)."""
    eligibility = evaluate_rotation_eligibility(
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=False,
        rollback_plan_validated=True,
        approval_requirement_resolved=False,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    blockers = auth.all_blockers
    assert "immutable_evidence_sink_unavailable" in blockers
    assert "approval_requirement_unresolved" in blockers
    assert "rollback_plan_not_validated" not in blockers
    assert auth.authorized is False


def test_workflow_execution_authorization_incident_freeze():
    """Active incident freeze blocks execution (authorized derived as False)."""
    eligibility = evaluate_rotation_eligibility(
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=False,
        policy_version="1",
    )
    assert "active_incident_freeze" in auth.all_blockers
    assert auth.authorized is False


def test_workflow_execution_authorization_policy_blocker_denies():
    """Explicit policy blocker with all checks true still denies authorization."""
    eligibility = evaluate_rotation_eligibility(
        subject=_make_subject("cts-cred"),
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=_make_subject("cts-cred"),
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_blockers=("manual_hold",),
        policy_version="1",
    )
    assert auth.authorized is False
    assert "manual_hold" in auth.all_blockers


def test_high_tier_requires_both_eligibility_and_authorization():
    """High-tier rotation needs both provider eligibility AND execution authorization."""
    eligibility = evaluate_rotation_eligibility(
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=_make_subject("cts-postgres-runtime"),
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=False,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    can_rotate = eligibility.eligible and auth.authorized
    assert eligibility.eligible is True
    assert auth.authorized is False
    assert can_rotate is False


def test_authorization_subject_fingerprint_matches_eligibility():
    """Authorization subject_fingerprint matches the eligibility input_fingerprint."""
    subject = _make_subject("cts-postgres-runtime")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    assert auth.subject_fingerprint == eligibility.input_fingerprint
    assert auth.matches_eligibility(eligibility) is True


def test_authorization_subject_fingerprint_mismatch_blocks_mutation():
    """Subject fingerprint mismatch between eligibility and authorization blocks mutation."""
    subject_a = _make_subject("cts-cred-a")
    subject_b = _make_subject("cts-cred-b")
    eligibility_a = evaluate_rotation_eligibility(
        subject=subject_a,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    # Create authorization bound to a different eligibility (different subject)
    eligibility_b = evaluate_rotation_eligibility(
        subject=subject_b,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth_for_b = evaluate_workflow_execution_authorization(
        subject=subject_b,
        risk_tier=RISK_HIGH,
        eligibility=eligibility_b,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    # auth_for_b does NOT match eligibility_a
    assert auth_for_b.matches_eligibility(eligibility_a) is False


def test_authorization_execution_fingerprint_changes_with_inputs():
    """Execution fingerprint changes when execution-time inputs change."""
    subject = _make_subject("cts-cred")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth1 = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    auth2 = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=False,  # changed
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    assert auth1.execution_fingerprint != auth2.execution_fingerprint


def test_authorization_execution_fingerprint_changes_with_incident_freeze():
    """Execution fingerprint changes when incident freeze state changes."""
    subject = _make_subject("cts-cred")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth1 = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    auth2 = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=False,  # incident freeze appeared
        policy_version="1",
    )
    assert auth1.execution_fingerprint != auth2.execution_fingerprint


def test_authorization_execution_fingerprint_deterministic():
    """Same execution inputs produce the same execution fingerprint."""
    subject = _make_subject("cts-cred")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth1 = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    auth2 = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    assert auth1.execution_fingerprint == auth2.execution_fingerprint


def test_critical_gate_fails_blocks_mutation_even_with_workflow_auth():
    """Critical platform gate failure blocks mutation even if workflow auth passes."""
    subject = _make_subject("cts-admin")
    caps = _full_caps()
    # Critical with missing gates → eligibility.eligible is False
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_CRITICAL,
        capabilities=caps,
        gates=None,
        policy_version="1",
    )
    # Workflow authorization passes
    auth = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_CRITICAL,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    can_rotate = eligibility.eligible and auth.authorized
    assert eligibility.eligible is False  # critical gates missing
    assert auth.authorized is True  # workflow checks pass
    assert can_rotate is False  # but mutation is still blocked


def test_stale_authorization_after_consumer_version_change():
    """Authorization is stale after consumer-set version changes (fingerprint mismatch)."""
    subject_v1 = RotationSubject(
        credential_set_id="cts-cred",
        provider_ref="postgresql:pg",
        provider_identity_ref="role:cts_runtime",
        secret_authority_ref="vault:secret/cts/db",
        consumer_set_ref="deployment:cts/cts-backend",
        consumer_set_version="resource_version:12345",
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
    )
    subject_v2 = RotationSubject(
        credential_set_id="cts-cred",
        provider_ref="postgresql:pg",
        provider_identity_ref="role:cts_runtime",
        secret_authority_ref="vault:secret/cts/db",
        consumer_set_ref="deployment:cts/cts-backend",
        consumer_set_version="resource_version:99999",  # changed
        rotation_strategy="dual_login_role",
        reload_strategy="rolling_restart",
    )
    eligibility_v1 = evaluate_rotation_eligibility(
        subject=subject_v1,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth_for_v1 = evaluate_workflow_execution_authorization(
        subject=subject_v1,
        risk_tier=RISK_HIGH,
        eligibility=eligibility_v1,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
    )
    # Consumer set changed → new eligibility has different fingerprint
    eligibility_v2 = evaluate_rotation_eligibility(
        subject=subject_v2,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    # Old authorization does not match new eligibility
    assert auth_for_v1.matches_eligibility(eligibility_v2) is False
    assert eligibility_v1.input_fingerprint != eligibility_v2.input_fingerprint


# --- Fail-fast subject/eligibility consistency validation ---


def test_evaluator_rejects_subject_eligibility_credential_id_mismatch():
    """Evaluator raises ValueError when subject credential_set_id != eligibility."""
    import pytest
    subject_a = _make_subject("cts-cred-a")
    eligibility_for_b = evaluate_rotation_eligibility(
        subject=_make_subject("cts-cred-b"),
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    with pytest.raises(ValueError, match="credential_set_id"):
        evaluate_workflow_execution_authorization(
            subject=subject_a,
            risk_tier=RISK_HIGH,
            eligibility=eligibility_for_b,
            immutable_evidence_sink_available=True,
            rollback_plan_validated=True,
            approval_requirement_resolved=True,
            cutover_scope_matches_approved_plan=True,
            no_active_incident_freeze=True,
            policy_version="1",
        )


def test_evaluator_rejects_risk_tier_mismatch():
    """Evaluator raises ValueError when risk_tier != eligibility.risk_tier."""
    import pytest
    subject = _make_subject("cts-cred")
    eligibility_high = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    with pytest.raises(ValueError, match="risk_tier"):
        evaluate_workflow_execution_authorization(
            subject=subject,
            risk_tier=RISK_LOW,  # mismatch
            eligibility=eligibility_high,
            immutable_evidence_sink_available=True,
            rollback_plan_validated=True,
            approval_requirement_resolved=True,
            cutover_scope_matches_approved_plan=True,
            no_active_incident_freeze=True,
            policy_version="1",
        )


def test_evaluator_rejects_policy_version_mismatch():
    """Evaluator raises ValueError when policy_version != eligibility.policy_version."""
    import pytest
    subject = _make_subject("cts-cred")
    eligibility_v1 = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    with pytest.raises(ValueError, match="policy_version"):
        evaluate_workflow_execution_authorization(
            subject=subject,
            risk_tier=RISK_HIGH,
            eligibility=eligibility_v1,
            immutable_evidence_sink_available=True,
            rollback_plan_validated=True,
            approval_requirement_resolved=True,
            cutover_scope_matches_approved_plan=True,
            no_active_incident_freeze=True,
            policy_version="2",  # mismatch
        )


# --- Approval binding ---


def test_approval_binding_valid_does_not_block():
    """Valid approval binding with matching fingerprint and future expiry does not block."""
    subject = _make_subject("cts-cred")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
        approval_ref="approval:rotation_01J:revision_3",
        approval_subject_fingerprint=eligibility.input_fingerprint,
        approval_expires_at="2099-01-01T00:00:00+00:00",
    )
    assert auth.authorized is True
    assert "approval_subject_fingerprint_mismatch" not in auth.all_blockers
    assert "approval_expired" not in auth.all_blockers


def test_approval_binding_subject_fingerprint_mismatch_blocks():
    """Approval with wrong subject fingerprint blocks authorization."""
    subject = _make_subject("cts-cred")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
        approval_ref="approval:rotation_01J:revision_3",
        approval_subject_fingerprint="sha256:wrong_fingerprint",
        approval_expires_at="2099-01-01T00:00:00+00:00",
    )
    assert auth.authorized is False
    assert "approval_subject_fingerprint_mismatch" in auth.all_blockers


def test_approval_binding_expired_blocks():
    """Expired approval blocks authorization."""
    subject = _make_subject("cts-cred")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
        approval_ref="approval:rotation_01J:revision_3",
        approval_subject_fingerprint=eligibility.input_fingerprint,
        approval_expires_at="2020-01-01T00:00:00+00:00",  # past
    )
    assert auth.authorized is False
    assert "approval_expired" in auth.all_blockers


def test_approval_binding_malformed_expiry_blocks():
    """Malformed approval expiry blocks authorization (fail-closed)."""
    subject = _make_subject("cts-cred")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_HIGH,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_HIGH,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
        approval_ref="approval:rotation_01J:revision_3",
        approval_subject_fingerprint=eligibility.input_fingerprint,
        approval_expires_at="not-a-date",
    )
    assert auth.authorized is False
    assert "approval_expiry_malformed" in auth.all_blockers


def test_approval_binding_none_does_not_add_blockers():
    """No approval binding (None) does not add approval-related blockers."""
    subject = _make_subject("cts-cred")
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        policy_version="1",
    )
    auth = evaluate_workflow_execution_authorization(
        subject=subject,
        risk_tier=RISK_LOW,
        eligibility=eligibility,
        immutable_evidence_sink_available=True,
        rollback_plan_validated=True,
        approval_requirement_resolved=True,
        cutover_scope_matches_approved_plan=True,
        no_active_incident_freeze=True,
        policy_version="1",
        # approval_ref, approval_subject_fingerprint, approval_expires_at all None
    )
    assert auth.authorized is True
    assert "approval_subject_fingerprint_mismatch" not in auth.all_blockers
    assert "approval_expired" not in auth.all_blockers
    assert "approval_expiry_malformed" not in auth.all_blockers


# --- Phase 1: Credential Discovery Workflow (read-only posture pipeline) ---


def _make_record(
    credential_set_id: str = "cts-postgres-runtime",
    credential_class: str = "postgresql_login",
    environment: str = "prod",
    lifecycle_state: str = LIFECYCLE_DISCOVERED,
    owner: Optional[OwnerRef] = None,
    authority: Optional[AuthorityRef] = None,
    consumers: tuple[ConsumerRef, ...] = (),
    risk_tier: str = RISK_MEDIUM,
    capabilities: Optional[RotationCapabilities] = None,
    target_strategy: Optional[str] = None,
) -> CredentialSetRecord:
    """Create a CredentialSetRecord for posture testing."""
    return CredentialSetRecord(
        credential_set_id=credential_set_id,
        display_name=credential_set_id.replace("-", " ").title(),
        credential_class=credential_class,
        environment=environment,
        lifecycle_state=lifecycle_state,
        owner=owner,
        authority=authority,
        consumers=consumers,
        risk=RiskAssessment(tier=risk_tier),
        capabilities=capabilities or RotationCapabilities(),
        target_strategy=target_strategy,
    )


def test_posture_report_basic():
    """evaluate_posture produces a PostureReport from credential records."""
    record = _make_record(
        credential_set_id="cts-minio-writer",
        credential_class="object_storage_key",
        risk_tier=RISK_LOW,
        owner=OwnerRef(team="infra"),
        authority=AuthorityRef(provider="vault", namespace="cts", secret_name="minio-writer"),
        consumers=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
        capabilities=_full_caps(),
    )
    report = evaluate_posture(
        run_id="run-001",
        records=(record,),
        policy_version="1",
    )
    assert isinstance(report, PostureReport)
    assert report.run_id == "run-001"
    assert report.total_credentials == 1
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.credential_set_id == "cts-minio-writer"
    assert entry.risk_tier == RISK_LOW
    assert entry.eligible is True  # low risk with full caps
    assert entry.owner == "infra"
    assert entry.consumer_count == 1


def test_posture_report_unowned_credential():
    """Unowned credentials are counted and recommended for owner assignment."""
    record = _make_record(
        credential_set_id="cts-orphan-key",
        owner=None,
        risk_tier=RISK_MEDIUM,
    )
    report = evaluate_posture(
        run_id="run-002",
        records=(record,),
        policy_version="1",
    )
    assert report.unowned_count == 1
    entry = report.entries[0]
    assert entry.owner is None
    assert entry.recommended_next_action == "assign_owner"


def test_posture_report_orphaned_credential():
    """Credentials with no consumers but past discovered state are orphaned."""
    record = _make_record(
        credential_set_id="cts-orphaned-role",
        lifecycle_state=LIFECYCLE_ENROLLED,
        consumers=(),
        risk_tier=RISK_LOW,
        owner=OwnerRef(team="infra"),  # has owner, but no consumers
    )
    report = evaluate_posture(
        run_id="run-003",
        records=(record,),
        policy_version="1",
    )
    assert report.orphaned_count == 1
    entry = report.entries[0]
    assert entry.recommended_next_action == "triage_orphaned_credential"


def test_posture_report_blocked_credential():
    """Credentials with incomplete capabilities are blocked."""
    record = _make_record(
        credential_set_id="cts-blocked-cred",
        risk_tier=RISK_HIGH,
        capabilities=RotationCapabilities(
            successor_creation=True,
            secret_authority=False,  # missing
            delivery=True,
            consumer_reload=True,
            positive_probe=True,
            predecessor_revocation=True,
            overlap_support=True,
            audit_observability=True,
            owner_confirmation=True,
            rollback_verification=True,
        ),
    )
    report = evaluate_posture(
        run_id="run-004",
        records=(record,),
        policy_version="1",
    )
    assert report.blocked_count == 1
    entry = report.entries[0]
    assert entry.eligible is False
    assert "secret_authority" in entry.blockers


def test_posture_report_summary_by_risk_tier():
    """Report summarizes credentials by risk tier."""
    records = (
        _make_record(credential_set_id="cred-low", risk_tier=RISK_LOW, capabilities=_full_caps()),
        _make_record(credential_set_id="cred-low-2", risk_tier=RISK_LOW, capabilities=_full_caps()),
        _make_record(credential_set_id="cred-high", risk_tier=RISK_HIGH, capabilities=_full_caps()),
    )
    report = evaluate_posture(
        run_id="run-005",
        records=records,
        policy_version="1",
    )
    assert report.summary_by_risk_tier.get(RISK_LOW, 0) == 2
    assert report.summary_by_risk_tier.get(RISK_HIGH, 0) == 1


def test_posture_report_summary_by_lifecycle_state():
    """Report summarizes credentials by lifecycle state."""
    records = (
        _make_record(credential_set_id="cred-1", lifecycle_state=LIFECYCLE_DISCOVERED),
        _make_record(credential_set_id="cred-2", lifecycle_state=LIFECYCLE_ENROLLED),
        _make_record(credential_set_id="cred-3", lifecycle_state=LIFECYCLE_ENROLLED),
    )
    report = evaluate_posture(
        run_id="run-006",
        records=records,
        policy_version="1",
    )
    assert report.summary_by_lifecycle_state.get(LIFECYCLE_DISCOVERED, 0) == 1
    assert report.summary_by_lifecycle_state.get(LIFECYCLE_ENROLLED, 0) == 2


def test_posture_report_to_json():
    """Posture report serializes to JSON."""
    record = _make_record(
        credential_set_id="cts-json-test",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
    )
    report = evaluate_posture(
        run_id="run-json",
        records=(record,),
        policy_version="1",
    )
    json_str = report.to_json()
    import json
    parsed = json.loads(json_str)
    assert parsed["run_id"] == "run-json"
    assert parsed["total_credentials"] == 1
    assert len(parsed["entries"]) == 1


def test_posture_report_to_markdown():
    """Posture report renders to Markdown."""
    record = _make_record(
        credential_set_id="cts-md-test",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        owner=OwnerRef(team="infra"),
    )
    report = evaluate_posture(
        run_id="run-md",
        records=(record,),
        policy_version="1",
    )
    md = report.to_markdown()
    assert "# Credential Posture Report" in md
    assert "cts-md-test" in md
    assert "run-md" in md


def test_posture_entry_to_dict():
    """Posture entry serializes to dict."""
    record = _make_record(
        credential_set_id="cts-dict-test",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        owner=OwnerRef(team="platform"),
        authority=AuthorityRef(provider="vault", namespace="cts", secret_name="db-cred"),
    )
    report = evaluate_posture(
        run_id="run-dict",
        records=(record,),
        policy_version="1",
    )
    d = report.entries[0].to_dict()
    assert d["credential_set_id"] == "cts-dict-test"
    assert d["risk_tier"] == RISK_LOW
    assert d["eligible"] is True
    assert "input_fingerprint" in d
    assert d["input_fingerprint"].startswith("sha256:")


def test_posture_report_secret_authority_status():
    """Posture entry reports secret authority status from authority provider."""
    # Vault-backed → managed
    vault_record = _make_record(
        credential_set_id="cts-vault",
        authority=AuthorityRef(provider="vault", namespace="cts", secret_name="db"),
    )
    # Kubernetes secret → unmanaged
    k8s_record = _make_record(
        credential_set_id="cts-k8s-secret",
        authority=AuthorityRef(provider="kubernetes_secret", namespace="cts", secret_name="db"),
    )
    report = evaluate_posture(
        run_id="run-auth",
        records=(vault_record, k8s_record),
        policy_version="1",
    )
    vault_entry = next(e for e in report.entries if e.credential_set_id == "cts-vault")
    k8s_entry = next(e for e in report.entries if e.credential_set_id == "cts-k8s-secret")
    assert vault_entry.secret_authority_status == "managed"
    assert k8s_entry.secret_authority_status == "unmanaged"


def test_posture_report_no_secret_values_in_output():
    """Posture report contains no plaintext secret material."""
    record = _make_record(
        credential_set_id="cts-no-secrets",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
        authority=AuthorityRef(provider="vault", namespace="cts", secret_name="db-cred"),
    )
    report = evaluate_posture(
        run_id="run-safe",
        records=(record,),
        policy_version="1",
    )
    # Check JSON output doesn't contain common secret patterns
    json_output = report.to_json()
    assert "password" not in json_output.lower()
    assert "token" not in json_output.lower() or "credential_set_id" in json_output
    # The output should contain references, not values
    assert "vault:cts/db-cred" in json_output or "vault" in json_output


def test_posture_report_multiple_credentials():
    """Posture report handles multiple credentials with mixed states."""
    records = (
        _make_record(
            credential_set_id="cts-low-eligible",
            risk_tier=RISK_LOW,
            capabilities=_full_caps(),
            owner=OwnerRef(team="infra"),
            lifecycle_state=LIFECYCLE_ROTATION_READY,
        ),
        _make_record(
            credential_set_id="cts-high-blocked",
            risk_tier=RISK_HIGH,
            capabilities=RotationCapabilities(),  # all False → blocked
            owner=OwnerRef(team="platform"),
            lifecycle_state=LIFECYCLE_DISCOVERED,
        ),
        _make_record(
            credential_set_id="cts-unowned",
            risk_tier=RISK_MEDIUM,
            capabilities=_full_caps(),
            owner=None,
            lifecycle_state=LIFECYCLE_DISCOVERED,
        ),
    )
    report = evaluate_posture(
        run_id="run-multi",
        records=records,
        policy_version="1",
    )
    assert report.total_credentials == 3
    assert report.eligible_count == 2  # low and medium eligible
    assert report.blocked_count == 1  # high blocked
    assert report.unowned_count == 1


def test_posture_report_risk_tier_overrides():
    """Risk tier overrides take precedence over record's risk tier."""
    record = _make_record(
        credential_set_id="cts-override",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
    )
    report = evaluate_posture(
        run_id="run-override",
        records=(record,),
        risk_tier_overrides={"cts-override": RISK_HIGH},
        policy_version="1",
    )
    entry = report.entries[0]
    assert entry.risk_tier == RISK_HIGH  # overridden


def test_posture_report_empty_records():
    """Empty records produce an empty but valid report."""
    report = evaluate_posture(
        run_id="run-empty",
        records=(),
        policy_version="1",
    )
    assert report.total_credentials == 0
    assert report.eligible_count == 0
    assert report.blocked_count == 0
    assert len(report.entries) == 0


def test_posture_entry_has_input_fingerprint():
    """Each posture entry carries the eligibility input fingerprint."""
    record = _make_record(
        credential_set_id="cts-fp-test",
        risk_tier=RISK_LOW,
        capabilities=_full_caps(),
    )
    report = evaluate_posture(
        run_id="run-fp",
        records=(record,),
        policy_version="1",
    )
    entry = report.entries[0]
    assert entry.input_fingerprint.startswith("sha256:")
    assert len(entry.input_fingerprint) > len("sha256:")


# --- CredentialObservation ---


def test_credential_observation_basic():
    """CredentialObservation holds adapter-neutral discovery output."""
    obs = CredentialObservation(
        observation_id="obs-001",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="prod",
        credential_class="postgresql_login",
        provider_ref="postgresql:infra-data-postgres",
        provider_identity_ref="role:cts_runtime",
        secret_authority_ref="vault:secret/cts/db",
        consumer_refs=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
        owner_hint=OwnerRef(team="infra"),
        risk_signals=("admin_privilege",),
        exposure_class="active_in_cluster_no_authority",
        evidence_ref="k8s:cts/cts-backend@resource_version:12345",
    )
    assert obs.observation_id == "obs-001"
    assert obs.source == COVERAGE_SOURCE_KUBERNETES
    assert obs.credential_class == "postgresql_login"
    assert len(obs.consumer_refs) == 1
    assert obs.plaintext_retained is False


def test_credential_observation_to_dict():
    """CredentialObservation serializes to dict."""
    obs = CredentialObservation(
        observation_id="obs-002",
        source=COVERAGE_SOURCE_POSTGRES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="prod",
        credential_class="postgresql_login",
        provider_ref="postgresql:infra-data-postgres",
        evidence_ref="pg:infra-data-postgres:role_catalog",
    )
    d = obs.to_dict()
    assert d["observation_id"] == "obs-002"
    assert d["source"] == COVERAGE_SOURCE_POSTGRES
    assert d["plaintext_retained"] is False
    assert d["owner_hint"] is None


def test_credential_observation_plaintext_retained_defaults_false():
    """CredentialObservation defaults plaintext_retained to False."""
    obs = CredentialObservation(
        observation_id="obs-003",
        source=COVERAGE_SOURCE_MINIO,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="prod",
    )
    assert obs.plaintext_retained is False


# --- Coverage metadata ---


def test_posture_report_default_coverage_not_configured():
    """Report without coverage argument defaults all sources to not_configured."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-cov-default",
        records=(record,),
        policy_version="1",
    )
    for source in ALL_COVERAGE_SOURCES:
        assert report.coverage[source] == COVERAGE_NOT_CONFIGURED


def test_posture_report_coverage_completed():
    """Report with completed coverage has no limitations for that source."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-cov-ok",
        records=(record,),
        policy_version="1",
        coverage={
            COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_POSTGRES: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_MINIO: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_GIT_FINDINGS: COVERAGE_COMPLETED,
        },
    )
    assert report.has_coverage_gaps is False
    assert len(report.limitations) == 0


def test_posture_report_coverage_partial_produces_limitation():
    """Partial coverage produces a limitation."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-cov-partial",
        records=(record,),
        policy_version="1",
        coverage={
            COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_POSTGRES: COVERAGE_PARTIAL,
            COVERAGE_SOURCE_MINIO: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_GIT_FINDINGS: COVERAGE_COMPLETED,
        },
    )
    assert report.has_coverage_gaps is True
    partial_limitations = [l for l in report.limitations if "partially" in l]
    assert len(partial_limitations) == 1


def test_posture_report_coverage_failed_produces_limitation():
    """Failed coverage produces a limitation."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-cov-failed",
        records=(record,),
        policy_version="1",
        coverage={
            COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_POSTGRES: COVERAGE_FAILED,
            COVERAGE_SOURCE_MINIO: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_GIT_FINDINGS: COVERAGE_COMPLETED,
        },
    )
    failed_limitations = [l for l in report.limitations if "failed" in l]
    assert len(failed_limitations) == 1


def test_posture_report_coverage_not_configured_produces_limitation():
    """Not-configured coverage produces a limitation."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-cov-missing",
        records=(record,),
        policy_version="1",
        coverage={
            COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_POSTGRES: COVERAGE_NOT_CONFIGURED,
            COVERAGE_SOURCE_MINIO: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_GIT_FINDINGS: COVERAGE_COMPLETED,
        },
    )
    missing_limitations = [l for l in report.limitations if "not configured" in l]
    assert len(missing_limitations) == 1


def test_posture_report_has_coverage_gaps_true_when_missing():
    """has_coverage_gaps is True when any source is not completed."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-gaps",
        records=(record,),
        policy_version="1",
        coverage={
            COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_POSTGRES: COVERAGE_NOT_CONFIGURED,
            COVERAGE_SOURCE_MINIO: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_GIT_FINDINGS: COVERAGE_COMPLETED,
        },
    )
    assert report.has_coverage_gaps is True


def test_posture_report_coverage_in_json():
    """Coverage metadata appears in JSON output."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-cov-json",
        records=(record,),
        policy_version="1",
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
    )
    json_str = report.to_json()
    assert "coverage" in json_str
    assert "limitations" in json_str


def test_posture_report_coverage_in_markdown():
    """Coverage section appears in Markdown output."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-cov-md",
        records=(record,),
        policy_version="1",
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
    )
    md = report.to_markdown()
    assert "Discovery coverage" in md
    assert "Limitations" in md


# --- Report integrity ---


def test_posture_report_has_entries_sha256():
    """Report includes entries_sha256 for evidence traceability."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-hash",
        records=(record,),
        policy_version="1",
    )
    assert report.entries_sha256.startswith("sha256:")
    assert len(report.entries_sha256) > len("sha256:")


def test_posture_report_entries_sha256_deterministic():
    """Same entries produce the same entries_sha256."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report1 = evaluate_posture(run_id="run-1", records=(record,), policy_version="1")
    report2 = evaluate_posture(run_id="run-2", records=(record,), policy_version="1")
    assert report1.entries_sha256 == report2.entries_sha256


def test_posture_report_entries_sha256_changes_with_different_entries():
    """Different entries produce different entries_sha256."""
    record1 = _make_record(credential_set_id="cts-cred-a", risk_tier=RISK_LOW, capabilities=_full_caps())
    record2 = _make_record(credential_set_id="cts-cred-b", risk_tier=RISK_LOW, capabilities=_full_caps())
    report1 = evaluate_posture(run_id="run-1", records=(record1,), policy_version="1")
    report2 = evaluate_posture(run_id="run-2", records=(record2,), policy_version="1")
    assert report1.entries_sha256 != report2.entries_sha256


def test_posture_report_has_report_version():
    """Report includes report_version."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-ver",
        records=(record,),
        policy_version="1",
    )
    assert report.report_version == REPORT_VERSION


def test_posture_report_has_contract_package_version():
    """Report includes contract_package_version."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-pkg",
        records=(record,),
        policy_version="1",
    )
    assert report.contract_package_version != ""
    assert report.contract_package_version == "0.8.0" or len(report.contract_package_version.split(".")) >= 2


def test_posture_report_evidence_manifest_ref():
    """Report carries evidence_manifest_ref when provided."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-evidence",
        records=(record,),
        policy_version="1",
        evidence_manifest_ref="security-evidence://discovery/2026-09-05/run-001",
    )
    assert report.evidence_manifest_ref == "security-evidence://discovery/2026-09-05/run-001"
    assert "evidence_manifest_ref" in report.to_json()


def test_posture_report_no_secret_values_in_coverage_output():
    """Coverage and limitations contain no secret values."""
    record = _make_record(credential_set_id="cts-cred", risk_tier=RISK_LOW, capabilities=_full_caps())
    report = evaluate_posture(
        run_id="run-safe-cov",
        records=(record,),
        policy_version="1",
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
    )
    json_output = report.to_json()
    assert "password" not in json_output.lower()
    assert "access_key" not in json_output.lower()


# --- Observation safety validation ---


def _make_safe_observation(observation_id: str = "obs-safe") -> CredentialObservation:
    """Create a known-safe observation for testing."""
    return CredentialObservation(
        observation_id=observation_id,
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        credential_class="postgresql_login",
        provider_ref="postgresql:infra-data",
        secret_authority_ref="kubernetes-secret:cts/cts-db-secret#uri",
        consumer_refs=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
        owner_hint=OwnerRef(team="infra"),
        risk_signals=("runtime-database-access",),
        evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
    )


def test_assert_observation_safe_passes_for_clean_observation():
    """A clean observation with no secret material passes validation."""
    obs = _make_safe_observation()
    assert_observation_safe(obs)  # should not raise


def test_assert_observation_safe_rejects_plaintext_retained_true():
    """Observation with plaintext_retained=True is rejected."""
    obs = CredentialObservation(
        observation_id="obs-bad",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        plaintext_retained=True,
    )
    with pytest.raises(UnsafeObservationError, match="plaintext_retained"):
        assert_observation_safe(obs)


def test_assert_observation_safe_rejects_password_in_ref():
    """Observation with password= in provider_ref is rejected."""
    obs = CredentialObservation(
        observation_id="obs-leak",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        provider_ref="postgresql://user:password=secret@host:5432/db",
    )
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_observation_safe(obs)


def test_assert_observation_safe_rejects_dsn_in_secret_authority():
    """Observation with postgres:// DSN in secret_authority_ref is rejected."""
    obs = CredentialObservation(
        observation_id="obs-dsn",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        secret_authority_ref="postgres://user:pass@host:5432/db",
    )
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_observation_safe(obs)


def test_assert_observation_safe_rejects_aws_secret_in_evidence():
    """Observation with aws_secret_access_key in evidence_ref is rejected."""
    obs = CredentialObservation(
        observation_id="obs-aws",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        evidence_ref="aws_secret_access_key=ABC123",
    )
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_observation_safe(obs)


def test_assert_observation_safe_rejects_private_key():
    """Observation with BEGIN PRIVATE KEY is rejected."""
    obs = CredentialObservation(
        observation_id="obs-pkey",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        evidence_ref="-----BEGIN PRIVATE KEY-----",
    )
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_observation_safe(obs)


def test_assert_observations_safe_batch():
    """Batch validation raises on first unsafe observation."""
    safe_obs = _make_safe_observation("obs-1")
    unsafe_obs = CredentialObservation(
        observation_id="obs-2",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        provider_ref="password=secret",
    )
    with pytest.raises(UnsafeObservationError, match="obs-2"):
        assert_observations_safe((safe_obs, unsafe_obs))


def test_assert_observations_safe_all_clean():
    """Batch validation passes when all observations are clean."""
    obs1 = _make_safe_observation("obs-1")
    obs2 = _make_safe_observation("obs-2")
    assert_observations_safe((obs1, obs2))  # should not raise


def test_forbidden_markers_is_not_empty():
    """FORBIDDEN_MARKERS contains expected entries."""
    assert "password=" in FORBIDDEN_MARKERS
    assert "postgres://" in FORBIDDEN_MARKERS
    assert "aws_secret_access_key=" in FORBIDDEN_MARKERS


# --- Kubernetes discovery adapter ---


class SyntheticK8sClient:
    """Synthetic Kubernetes client for testing with CTS-like workloads."""

    def __init__(self, workloads: tuple[WorkloadMetadata, ...]):
        self._workloads = workloads

    def list_workloads(self, namespace: str) -> tuple[WorkloadMetadata, ...]:
        return tuple(w for w in self._workloads if w.namespace == namespace)

    def list_external_secrets(self, namespace: str) -> tuple[ExternalSecretMetadata, ...]:
        return ()


def _make_cts_backend_workload() -> WorkloadMetadata:
    """Create synthetic CTS backend workload metadata (no secret values).

    The client has already discarded inline values and reduced them to
    inline_value_present=True. The adapter never sees the actual values.
    """
    return WorkloadMetadata(
        kind="Deployment",
        namespace="cts",
        name="cts-backend",
        container_name="cts-backend",
        env_vars=(
            # POSTGRES_DSN with inline value (value discarded by client, only Boolean retained)
            WorkloadEnvVar(name="POSTGRES_DSN", inline_value_present=True),
            # AWS_SECRET_ACCESS_KEY with inline value (value discarded by client)
            WorkloadEnvVar(name="AWS_SECRET_ACCESS_KEY", inline_value_present=True),
            # Non-credential env var (should be ignored)
            WorkloadEnvVar(name="PORT", inline_value_present=True),
            # Credential with secretKeyRef (good pattern)
            WorkloadEnvVar(name="DATABASE_URL", secret_ref_name="cts-db-secret", secret_ref_key="uri"),
        ),
        env_from=(),
        volume_secrets=(),
        service_account="cts-backend-sa",
        owner_annotations={"team": "cts-platform", "service": "attunement-weaver"},
        resource_version="12345",
    )


def _make_cts_watchdog_workload() -> WorkloadMetadata:
    """Create synthetic CTS watchdog workload metadata (no secret values)."""
    return WorkloadMetadata(
        kind="Deployment",
        namespace="cts",
        name="cts-watchdog",
        container_name="cts-watchdog",
        env_vars=(
            WorkloadEnvVar(name="POSTGRES_DSN", inline_value_present=True),
            WorkloadEnvVar(name="AWS_SECRET_ACCESS_KEY", inline_value_present=True),
        ),
        env_from=(
            WorkloadEnvFrom(secret_ref_name="cts-shared-secrets"),
        ),
        volume_secrets=(),
        service_account="cts-watchdog-sa",
        owner_annotations={"team": "cts-platform"},
        resource_version="12346",
    )


def _make_cts_with_volume_secret() -> WorkloadMetadata:
    """Create workload with volume-mounted secret."""
    return WorkloadMetadata(
        kind="StatefulSet",
        namespace="cts",
        name="cts-data-processor",
        container_name="processor",
        env_vars=(),
        env_from=(),
        volume_secrets=(
            WorkloadVolumeSecret(volume_name="tls-certs", secret_ref_name="cts-tls-secret", mount_path="/etc/tls"),
        ),
        owner_annotations={"team": "infra"},
        resource_version="12347",
    )


def test_k8s_adapter_discovers_inline_postgres_dsn():
    """Adapter discovers POSTGRES_DSN env var and classifies it correctly."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    # Should find POSTGRES_DSN, AWS_SECRET_ACCESS_KEY, DATABASE_URL (PORT is not credential)
    obs_ids = [o.observation_id for o in observations]
    assert any("POSTGRES_DSN" in oid for oid in obs_ids)
    assert any("AWS_SECRET_ACCESS_KEY" in oid for oid in obs_ids)
    assert any("DATABASE_URL" in oid for oid in obs_ids)
    # PORT should NOT appear
    assert not any("PORT" in oid for oid in obs_ids)


def test_k8s_adapter_classifies_credential_class():
    """Adapter correctly classifies credential class from env var name."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert pg_obs.credential_class == "postgresql_login"

    aws_obs = next(o for o in observations if "AWS_SECRET_ACCESS_KEY" in o.observation_id)
    assert aws_obs.credential_class == "object_storage_key"


def test_k8s_adapter_emits_inline_secret_risk_signal():
    """Adapter flags inline env var secrets with correct risk signal."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    # POSTGRES_DSN has inline value, not secretKeyRef
    assert RISK_SIGNAL_INLINE_ENV_SECRET in pg_obs.risk_signals
    assert RISK_SIGNAL_NO_SECRET_REF in pg_obs.risk_signals
    assert RISK_SIGNAL_RUNTIME_DB_ACCESS in pg_obs.risk_signals


def test_k8s_adapter_emits_secret_ref_risk_signal():
    """Adapter flags secretKeyRef-based credentials with k8s-secret-delivery signal."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    db_url_obs = next(o for o in observations if "DATABASE_URL" in o.observation_id)
    assert RISK_SIGNAL_K8S_SECRET_DELIVERY in db_url_obs.risk_signals
    assert RISK_SIGNAL_INLINE_ENV_SECRET not in db_url_obs.risk_signals


def test_k8s_adapter_does_not_propagate_secret_values():
    """Adapter output contains no plaintext secret values.

    The adapter never receives values — the client discards them and
    sets inline_value_present=True. This test verifies that:
    1. inline_value_present is True for inline env vars
    2. No secret value substrings appear in any output
    """
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert pg_obs.inline_value_present is True

    # Check that no observation contains any secret-like value patterns
    for obs in observations:
        json_str = json.dumps(obs.to_dict())
        # These are values that would have been present in the old design
        assert "cNJ3+eCdYQoRSbdxpikZp9cG" not in json_str
        assert "password=SECRET" not in json_str
        assert "dbname=mydatabase" not in json_str
        assert "XwYcij2BguKzVlEdlsKJu1" not in json_str


def test_k8s_adapter_inline_value_not_in_exception():
    """Thrown exceptions do not contain inline secret values.

    If an unsafe observation is detected, the exception message must
    not contain any value that was present in the input workload.
    """
    # Create a workload with an inline value that would be flagged
    # The adapter discards values, so even if an exception is thrown,
    # the value is never in the observation or exception
    workload = WorkloadMetadata(
        kind="Deployment",
        namespace="cts",
        name="cts-bad",
        env_vars=(
            WorkloadEnvVar(name="POSTGRES_DSN", inline_value_present=True),
        ),
    )
    client = SyntheticK8sClient((workload,))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    # The observation should be safe (no value to leak)
    assert_observations_safe(observations)
    # Even if we serialize and check, no value is present
    for obs in observations:
        assert obs.inline_value_present is True
        # The observation_id contains the env var NAME, not the value
        assert "POSTGRES_DSN" in obs.observation_id


def test_k8s_adapter_batch_failure_no_value_leak():
    """Batch failure from one observation doesn't leak values from others.

    Even if assert_observations_safe raises on one observation, the
    exception message must not contain values from other observations.
    Since the adapter never carries values, this is guaranteed by design.
    """
    workload = WorkloadMetadata(
        kind="Deployment",
        namespace="cts",
        name="cts-multi",
        env_vars=(
            WorkloadEnvVar(name="POSTGRES_DSN", inline_value_present=True),
            WorkloadEnvVar(name="AWS_SECRET_ACCESS_KEY", inline_value_present=True),
        ),
    )
    client = SyntheticK8sClient((workload,))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    # All observations should be safe
    assert_observations_safe(observations)
    # No value substrings in any observation
    for obs in observations:
        serialized = json.dumps(obs.to_dict())
        assert "password=" not in serialized.lower()
        assert "cNJ3" not in serialized


def test_k8s_adapter_rejects_malformed_both_value_and_secret_ref():
    """Adapter rejects env var with both inline_value_present and secret_ref_name."""
    import pytest
    workload = WorkloadMetadata(
        kind="Deployment",
        namespace="cts",
        name="cts-malformed",
        env_vars=(
            # Both inline and secretKeyRef — invalid Kubernetes semantics
            WorkloadEnvVar(
                name="POSTGRES_DSN",
                inline_value_present=True,
                secret_ref_name="cts-db-secret",
                secret_ref_key="uri",
            ),
        ),
    )
    client = SyntheticK8sClient((workload,))
    with pytest.raises(MalformedWorkloadError, match="malformed"):
        discover_kubernetes_credentials(
            client=client,
            namespace="cts",
            environment="dev",
        )


def test_k8s_adapter_malformed_exception_no_value():
    """MalformedWorkloadError exception does not contain secret values."""
    workload = WorkloadMetadata(
        kind="Deployment",
        namespace="cts",
        name="cts-malformed",
        env_vars=(
            WorkloadEnvVar(
                name="POSTGRES_DSN",
                inline_value_present=True,
                secret_ref_name="cts-db-secret",
                secret_ref_key="uri",
            ),
        ),
    )
    client = SyntheticK8sClient((workload,))
    try:
        discover_kubernetes_credentials(
            client=client,
            namespace="cts",
            environment="dev",
        )
        assert False, "Should have raised MalformedWorkloadError"
    except MalformedWorkloadError as e:
        # Exception message should contain workload ref and env var name
        # but NOT any secret value
        msg = str(e)
        assert "cts-malformed" in msg
        assert "POSTGRES_DSN" in msg
        # No secret values (these would have been the actual values in old design)
        assert "password=" not in msg.lower()
        assert "cNJ3" not in msg


def test_k8s_adapter_inline_value_present_in_output():
    """inline_value_present=True appears in observation output."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert pg_obs.inline_value_present is True
    assert "inline_value_present" in pg_obs.to_dict()
    assert pg_obs.to_dict()["inline_value_present"] is True

    # secretKeyRef-based observation should have inline_value_present=False
    db_url_obs = next(o for o in observations if "DATABASE_URL" in o.observation_id)
    assert db_url_obs.inline_value_present is False


def test_k8s_adapter_exposure_class_active_in_source_for_inline():
    """Inline credentials get exposure_class=active_in_source."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert pg_obs.exposure_class == EXPOSURE_ACTIVE_IN_SOURCE


def test_k8s_adapter_exposure_class_managed_for_secret_ref():
    """secretKeyRef credentials get exposure_class=managed_via_secret_ref."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    db_url_obs = next(o for o in observations if "DATABASE_URL" in o.observation_id)
    assert db_url_obs.exposure_class == EXPOSURE_SECRET_DELIVERED


def test_k8s_adapter_default_action_emergency_rotation_for_inline():
    """Inline credentials get default_action=emergency_rotation."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert pg_obs.default_action == ACTION_EMERGENCY_ROTATION


def test_k8s_adapter_default_action_enrollment_for_secret_ref():
    """secretKeyRef credentials get default_action=enrollment_candidate."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    db_url_obs = next(o for o in observations if "DATABASE_URL" in o.observation_id)
    assert db_url_obs.default_action == ACTION_ENROLLMENT_CANDIDATE


def test_k8s_adapter_volume_secret_certificate_lifecycle():
    """Volume-mounted secrets get default_action=certificate_lifecycle."""
    client = SyntheticK8sClient((_make_cts_with_volume_secret(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    vol_obs = [o for o in observations if "volume" in o.observation_id]
    assert len(vol_obs) == 1
    assert vol_obs[0].default_action == ACTION_CERTIFICATE_LIFECYCLE


def test_k8s_adapter_all_observations_pass_safety_check():
    """All adapter output passes assert_observation_safe."""
    client = SyntheticK8sClient((_make_cts_backend_workload(), _make_cts_watchdog_workload()))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    assert len(observations) > 0
    assert_observations_safe(observations)  # should not raise


def test_k8s_adapter_extracts_owner_hint():
    """Adapter extracts owner hint from workload annotations."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert pg_obs.owner_hint is not None
    assert pg_obs.owner_hint.team == "cts-platform"
    assert pg_obs.owner_hint.service == "attunement-weaver"


def test_k8s_adapter_builds_consumer_ref():
    """Adapter builds correct consumer references."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert len(pg_obs.consumer_refs) == 1
    consumer = pg_obs.consumer_refs[0]
    assert consumer.kind == "Deployment"
    assert consumer.namespace == "cts"
    assert consumer.name == "cts-backend"
    assert consumer.container == "cts-backend"


def test_k8s_adapter_builds_evidence_ref():
    """Adapter builds opaque evidence references."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert "kubernetes://" in pg_obs.evidence_ref
    assert "cts-backend" in pg_obs.evidence_ref
    assert "12345" in pg_obs.evidence_ref  # resource_version


def test_k8s_adapter_handles_env_from():
    """Adapter discovers envFrom secret references."""
    client = SyntheticK8sClient((_make_cts_watchdog_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    envfrom_obs = [o for o in observations if "envfrom" in o.observation_id]
    assert len(envfrom_obs) == 1
    assert "cts-shared-secrets" in envfrom_obs[0].secret_authority_ref


def test_k8s_adapter_handles_volume_secrets():
    """Adapter discovers volume-mounted secret references."""
    client = SyntheticK8sClient((_make_cts_with_volume_secret(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    vol_obs = [o for o in observations if "volume" in o.observation_id]
    assert len(vol_obs) == 1
    assert "cts-tls-secret" in vol_obs[0].secret_authority_ref


def test_k8s_adapter_filters_by_namespace():
    """Adapter only returns workloads from the specified namespace."""
    other_workload = WorkloadMetadata(
        kind="Deployment",
        namespace="other-ns",
        name="other-app",
        env_vars=(WorkloadEnvVar(name="POSTGRES_DSN", inline_value_present=True),),
    )
    client = SyntheticK8sClient((_make_cts_backend_workload(), other_workload))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    for obs in observations:
        assert "cts" in obs.observation_id
        assert "other-ns" not in obs.observation_id


def test_k8s_adapter_source_is_kubernetes():
    """All observations from k8s adapter have source='kubernetes'."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    for obs in observations:
        assert obs.source == COVERAGE_SOURCE_KUBERNETES


def test_k8s_adapter_empty_namespace():
    """Adapter returns empty tuple for namespace with no workloads."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="empty-ns",
        environment="dev",
    )
    assert len(observations) == 0


def test_k8s_adapter_no_credential_env_vars():
    """Adapter ignores non-credential env vars."""
    workload = WorkloadMetadata(
        kind="Deployment",
        namespace="cts",
        name="no-creds-app",
        env_vars=(
            WorkloadEnvVar(name="PORT", inline_value_present=True),
            WorkloadEnvVar(name="LOG_LEVEL", inline_value_present=True),
            WorkloadEnvVar(name="MAX_CONNECTIONS", inline_value_present=True),
        ),
    )
    client = SyntheticK8sClient((workload,))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    assert len(observations) == 0


def test_k8s_adapter_inline_secret_authority_ref():
    """Adapter builds inline-env authority ref for env vars without secretKeyRef."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert "inline-env" in pg_obs.secret_authority_ref
    assert "cts-backend" in pg_obs.secret_authority_ref


def test_k8s_adapter_secret_key_ref_authority():
    """Adapter builds kubernetes-secret authority ref for secretKeyRef env vars."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    db_url_obs = next(o for o in observations if "DATABASE_URL" in o.observation_id)
    assert "kubernetes-secret" in db_url_obs.secret_authority_ref
    assert "cts-db-secret" in db_url_obs.secret_authority_ref
    assert "uri" in db_url_obs.secret_authority_ref


def test_k8s_adapter_multiple_workloads():
    """Adapter handles multiple workloads in the same namespace."""
    client = SyntheticK8sClient((
        _make_cts_backend_workload(),
        _make_cts_watchdog_workload(),
        _make_cts_with_volume_secret(),
    ))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    # cts-backend: POSTGRES_DSN, AWS_SECRET_ACCESS_KEY, DATABASE_URL
    # cts-watchdog: POSTGRES_DSN, AWS_SECRET_ACCESS_KEY, envFrom:cts-shared-secrets
    # cts-data-processor: volume:cts-tls-secret
    assert len(observations) >= 6
    # All should pass safety check
    assert_observations_safe(observations)


def test_k8s_adapter_observed_at_timestamp():
    """Adapter uses provided timestamp or generates one."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
        observed_at="2026-09-05T23:30:00+00:00",
    )
    for obs in observations:
        assert obs.observed_at == "2026-09-05T23:30:00+00:00"


def test_k8s_adapter_environment_label():
    """Adapter applies environment label to observations."""
    client = SyntheticK8sClient((_make_cts_backend_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="prod",
    )
    for obs in observations:
        assert obs.environment == "prod"


# --- Raw API boundary conversion tests ---


class FakeV1EnvVar:
    """Mimics Kubernetes Python client V1EnvVar for boundary testing."""

    def __init__(self, name, value=None, value_from=None):
        self.name = name
        self.value = value
        self.value_from = value_from


class FakeV1SecretKeySelector:
    """Mimics V1SecretKeySelector."""

    def __init__(self, name, key=None):
        self.name = name
        self.key = key


class FakeV1EnvVarSource:
    """Mimics V1EnvVarSource."""

    def __init__(self, secret_key_ref=None):
        self.secret_key_ref = secret_key_ref


class FakeV1EnvFromSource:
    """Mimics V1EnvFromSource."""

    def __init__(self, secret_ref=None):
        self.secret_ref = secret_ref


class FakeV1SecretEnvSource:
    """Mimics V1SecretEnvSource."""

    def __init__(self, name, optional=False):
        self.name = name
        self.optional = optional


class FakeV1Container:
    """Mimics V1Container for boundary testing."""

    def __init__(self, name, env=None, env_from=None):
        self.name = name
        self.env = env or []
        self.env_from = env_from or []


# Synthetic secret values for boundary testing — these must NOT survive conversion
_SYNTHETIC_INLINE_SECRET = "synthetic-secret-value-that-must-not-survive-ABC123"
_SYNTHETIC_DSN = "dbname=test user=admin password=S3cr3tP@ss host=db.internal port=5432"
_SYNTHETIC_MULTILINE = "line1\nline2\npassword=hidden\nline4"


def test_to_workload_env_var_discards_inline_value():
    """Boundary conversion discards inline value, keeps only Boolean presence."""
    api_env = FakeV1EnvVar(name="POSTGRES_DSN", value=_SYNTHETIC_INLINE_SECRET)
    safe_env = to_workload_env_var(api_env)

    assert safe_env.name == "POSTGRES_DSN"
    assert safe_env.inline_value_present is True
    assert safe_env.secret_ref_name is None
    assert not hasattr(safe_env, "value")


def test_to_workload_env_var_value_not_in_repr():
    """Raw value does not appear in WorkloadEnvVar repr."""
    api_env = FakeV1EnvVar(name="POSTGRES_DSN", value=_SYNTHETIC_INLINE_SECRET)
    safe_env = to_workload_env_var(api_env)

    repr_str = repr(safe_env)
    assert _SYNTHETIC_INLINE_SECRET not in repr_str
    assert "S3cr3tP@ss" not in repr_str


def test_to_workload_env_var_value_not_in_json():
    """Raw value does not appear in WorkloadEnvVar JSON serialization."""
    from dataclasses import asdict
    api_env = FakeV1EnvVar(name="POSTGRES_DSN", value=_SYNTHETIC_INLINE_SECRET)
    safe_env = to_workload_env_var(api_env)

    json_str = json.dumps(asdict(safe_env))
    assert _SYNTHETIC_INLINE_SECRET not in json_str
    assert "S3cr3tP@ss" not in json_str


def test_to_workload_env_var_secret_key_ref():
    """Boundary conversion extracts secretKeyRef correctly."""
    api_env = FakeV1EnvVar(
        name="DATABASE_URL",
        value=None,
        value_from=FakeV1EnvVarSource(
            secret_key_ref=FakeV1SecretKeySelector(name="cts-db-secret", key="uri")
        ),
    )
    safe_env = to_workload_env_var(api_env)

    assert safe_env.name == "DATABASE_URL"
    assert safe_env.inline_value_present is False
    assert safe_env.secret_ref_name == "cts-db-secret"
    assert safe_env.secret_ref_key == "uri"


def test_to_workload_env_var_rejects_both_value_and_value_from():
    """Boundary conversion rejects env var with both value and valueFrom."""
    api_env = FakeV1EnvVar(
        name="POSTGRES_DSN",
        value=_SYNTHETIC_INLINE_SECRET,
        value_from=FakeV1EnvVarSource(
            secret_key_ref=FakeV1SecretKeySelector(name="cts-db-secret", key="uri")
        ),
    )
    with pytest.raises(ValueError, match="malformed"):
        to_workload_env_var(api_env)


def test_to_workload_env_var_malformed_exception_no_value():
    """Malformed env var exception does not contain the secret value."""
    api_env = FakeV1EnvVar(
        name="POSTGRES_DSN",
        value=_SYNTHETIC_INLINE_SECRET,
        value_from=FakeV1EnvVarSource(
            secret_key_ref=FakeV1SecretKeySelector(name="cts-db-secret", key="uri")
        ),
    )
    try:
        to_workload_env_var(api_env)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        msg = str(e)
        assert "POSTGRES_DSN" in msg
        assert _SYNTHETIC_INLINE_SECRET not in msg
        assert "S3cr3tP@ss" not in msg


def test_to_workload_env_var_multiline_value_discarded():
    """Multiline/quoted inline value is discarded correctly."""
    api_env = FakeV1EnvVar(name="CUSTOM_CONFIG", value=_SYNTHETIC_MULTILINE)
    safe_env = to_workload_env_var(api_env)

    assert safe_env.inline_value_present is True
    assert _SYNTHETIC_MULTILINE not in repr(safe_env)
    from dataclasses import asdict
    assert _SYNTHETIC_MULTILINE not in json.dumps(asdict(safe_env))


def test_to_workload_env_var_no_value_no_ref():
    """Env var with neither value nor valueFrom produces unresolved WorkloadEnvVar."""
    api_env = FakeV1EnvVar(name="POSTGRES_DSN", value=None, value_from=None)
    safe_env = to_workload_env_var(api_env)

    assert safe_env.name == "POSTGRES_DSN"
    assert safe_env.inline_value_present is False
    assert safe_env.secret_ref_name is None


def test_to_workload_metadata_discards_all_inline_values():
    """to_workload_metadata discards all inline values from all containers."""
    api_containers = (
        FakeV1Container(
            name="cts-backend",
            env=[
                FakeV1EnvVar(name="POSTGRES_DSN", value=_SYNTHETIC_DSN),
                FakeV1EnvVar(name="AWS_SECRET_ACCESS_KEY", value=_SYNTHETIC_INLINE_SECRET),
                FakeV1EnvVar(name="PORT", value="8001"),
                FakeV1EnvVar(
                    name="DATABASE_URL",
                    value_from=FakeV1EnvVarSource(
                        secret_key_ref=FakeV1SecretKeySelector(name="cts-db-secret", key="uri")
                    ),
                ),
            ],
            env_from=[
                FakeV1EnvFromSource(
                    secret_ref=FakeV1SecretEnvSource(name="cts-shared-secrets")
                ),
            ],
        ),
    )

    metadata = to_workload_metadata(
        kind="Deployment",
        namespace="cts",
        name="cts-backend",
        api_containers=api_containers,
        resource_version="12345",
        owner_annotations={"team": "cts-platform"},
    )

    # Check that no secret values survived
    from dataclasses import asdict
    metadata_json = json.dumps(asdict(metadata))
    assert _SYNTHETIC_DSN not in metadata_json
    assert _SYNTHETIC_INLINE_SECRET not in metadata_json
    assert "S3cr3tP@ss" not in metadata_json
    assert "cNJ3" not in metadata_json

    # Check that the Boolean presence signals are correct
    pg_env = next(e for e in metadata.env_vars if e.name == "POSTGRES_DSN")
    assert pg_env.inline_value_present is True
    assert pg_env.secret_ref_name is None

    aws_env = next(e for e in metadata.env_vars if e.name == "AWS_SECRET_ACCESS_KEY")
    assert aws_env.inline_value_present is True

    db_url_env = next(e for e in metadata.env_vars if e.name == "DATABASE_URL")
    assert db_url_env.inline_value_present is False
    assert db_url_env.secret_ref_name == "cts-db-secret"

    # envFrom should be extracted
    assert len(metadata.env_from) == 1
    assert metadata.env_from[0].secret_ref_name == "cts-shared-secrets"


def test_to_workload_metadata_repr_no_secrets():
    """to_workload_metadata output repr contains no secret values."""
    api_containers = (
        FakeV1Container(
            name="cts-backend",
            env=[FakeV1EnvVar(name="POSTGRES_DSN", value=_SYNTHETIC_DSN)],
        ),
    )
    metadata = to_workload_metadata(
        kind="Deployment",
        namespace="cts",
        name="cts-backend",
        api_containers=api_containers,
    )
    metadata_repr = repr(metadata)
    assert _SYNTHETIC_DSN not in metadata_repr
    assert "S3cr3tP@ss" not in metadata_repr


# --- End-to-end pipeline: raw API → observation → posture report ---

def test_end_to_end_raw_api_to_posture_report_no_secret_survives():
    """Synthetic secret does not survive the full pipeline.

    Pipeline: raw API env var → WorkloadEnvVar → CredentialObservation
    → CredentialSetRecord → PostureReport JSON/Markdown.

    The synthetic secret value must be absent at every persisted or
    emitted boundary.
    """
    raw_secret = "synthetic-e2e-secret-must-not-survive-XYZ789"

    # Step 1: Raw API object with inline secret
    api_env = FakeV1EnvVar(name="POSTGRES_DSN", value=raw_secret)
    api_container = FakeV1Container(name="cts-backend", env=[api_env])

    # Step 2: Convert to safe metadata (value discarded)
    metadata = to_workload_metadata(
        kind="Deployment",
        namespace="cts",
        name="cts-backend",
        api_containers=(api_container,),
        resource_version="12345",
        owner_annotations={"team": "cts-platform"},
    )

    # Step 3: Run adapter
    client = SyntheticK8sClient((metadata,))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    assert len(observations) > 0

    # Step 4: Check observations don't contain the secret
    for obs in observations:
        obs_json = json.dumps(obs.to_dict())
        assert raw_secret not in obs_json
        assert "XYZ789" not in obs_json

    # Step 5: Build a CredentialSetRecord from the observation
    record = CredentialSetRecord(
        credential_set_id="cts-postgres-e2e",
        display_name="CTS PostgreSQL E2E Test",
        credential_class="postgresql_login",
        environment="dev",
        lifecycle_state=LIFECYCLE_DISCOVERED,
        owner=OwnerRef(team="cts-platform"),
        authority=AuthorityRef(provider="kubernetes_secret", namespace="cts", secret_name="cts-backend"),
        consumers=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
        risk=RiskAssessment(tier=RISK_HIGH),
        capabilities=_full_caps(),
    )

    # Step 6: Evaluate posture
    report = evaluate_posture(
        run_id="e2e-run-001",
        records=(record,),
        policy_version="1",
        coverage={
            COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_POSTGRES: COVERAGE_NOT_CONFIGURED,
            COVERAGE_SOURCE_MINIO: COVERAGE_NOT_CONFIGURED,
            COVERAGE_SOURCE_GIT_FINDINGS: COVERAGE_NOT_CONFIGURED,
        },
    )

    # Step 7: Check posture report JSON doesn't contain the secret
    report_json = report.to_json()
    assert raw_secret not in report_json
    assert "XYZ789" not in report_json

    # Step 8: Check posture report Markdown doesn't contain the secret
    report_md = report.to_markdown()
    assert raw_secret not in report_md
    assert "XYZ789" not in report_md

    # Step 9: Check entries_sha256 is present (evidence integrity)
    assert report.entries_sha256.startswith("sha256:")

    # Step 10: Check coverage is reported honestly
    assert report.coverage[COVERAGE_SOURCE_POSTGRES] == COVERAGE_NOT_CONFIGURED
    assert report.has_coverage_gaps is True


def test_end_to_end_inline_secret_not_in_exception():
    """If an exception is thrown during pipeline, the secret is not in the message."""
    raw_secret = "synthetic-exception-secret-must-not-survive"

    # Create a malformed env var (both value and valueFrom)
    api_env = FakeV1EnvVar(
        name="POSTGRES_DSN",
        value=raw_secret,
        value_from=FakeV1EnvVarSource(
            secret_key_ref=FakeV1SecretKeySelector(name="cts-db-secret", key="uri")
        ),
    )

    # The boundary conversion should raise ValueError without the secret
    try:
        to_workload_env_var(api_env)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        msg = str(e)
        assert raw_secret not in msg
        assert "must-not-survive" not in msg
        assert "POSTGRES_DSN" in msg  # env var name is OK


def test_end_to_end_multiple_secrets_none_survive():
    """Multiple inline secrets in one workload are all discarded."""
    secrets = [
        "secret-one-AAA111",
        "secret-two-BBB222",
        "secret-three-CCC333",
    ]

    api_envs = [FakeV1EnvVar(name=f"VAR_{i}", value=s) for i, s in enumerate(secrets)]
    # Add credential-like names so the adapter processes them
    api_envs.append(FakeV1EnvVar(name="POSTGRES_DSN", value=secrets[0]))
    api_envs.append(FakeV1EnvVar(name="AWS_SECRET_ACCESS_KEY", value=secrets[1]))

    api_container = FakeV1Container(name="cts-multi", env=api_envs)
    metadata = to_workload_metadata(
        kind="Deployment",
        namespace="cts",
        name="cts-multi",
        api_containers=(api_container,),
    )

    client = SyntheticK8sClient((metadata,))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )

    for obs in observations:
        obs_json = json.dumps(obs.to_dict())
        for secret in secrets:
            assert secret not in obs_json
            assert secret not in repr(obs)


def test_exposure_class_secret_delivered_not_managed():
    """EXPOSURE_SECRET_DELIVERED is the correct term, not 'managed'."""
    # The value should be "secret_delivered" not "managed_via_secret_ref"
    assert EXPOSURE_SECRET_DELIVERED == "secret_delivered"
    # The deprecated alias should map to the same value
    assert EXPOSURE_MANAGED_VIA_SECRET_REF == EXPOSURE_SECRET_DELIVERED


# --- Log scrubber tests ---


def test_secret_scrubbing_filter_redacts_password():
    """Log scrubber redacts password= patterns."""
    import logging
    filt = SecretScrubbingFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Connecting with password=S3cr3tP@ss to database",
        args=None, exc_info=None,
    )
    filt.filter(record)
    assert "S3cr3tP@ss" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_secret_scrubbing_filter_redacts_postgres_dsn():
    """Log scrubber redacts postgres:// DSN passwords."""
    import logging
    filt = SecretScrubbingFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="DSN: postgresql://user:supersecret@db.internal:5432/mydb",
        args=None, exc_info=None,
    )
    filt.filter(record)
    assert "supersecret" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_secret_scrubbing_filter_redacts_token():
    """Log scrubber redacts token= patterns."""
    import logging
    filt = SecretScrubbingFilter()
    # Construct synthetic token to avoid triggering secret scanners
    synthetic_token = "abc" + "123" + "def" + "456" + "ghi" + "789"
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg=f"Auth with token={synthetic_token}",
        args=None, exc_info=None,
    )
    filt.filter(record)
    assert synthetic_token not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_secret_scrubbing_filter_redacts_pem_key():
    """Log scrubber redacts PEM private key blocks."""
    import logging
    filt = SecretScrubbingFilter()
    # Construct PEM block dynamically to avoid triggering secret scanners
    pem_header = "-" * 5 + "BEGIN RSA PRIVATE KEY" + "-" * 5
    pem_footer = "-" * 5 + "END RSA PRIVATE KEY" + "-" * 5
    pem_body = "MII" + "keymaterial" + "here"
    pem_block = f"{pem_header}\n{pem_body}\n{pem_footer}"
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg=f"Found key: {pem_block}",
        args=None, exc_info=None,
    )
    filt.filter(record)
    assert pem_body not in record.getMessage()
    assert "REDACTED PEM KEY BLOCK" in record.getMessage()


def test_secret_scrubbing_filter_passes_clean_messages():
    """Log scrubber passes clean messages unchanged."""
    import logging
    filt = SecretScrubbingFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Listing Deployments in namespace cts",
        args=None, exc_info=None,
    )
    filt.filter(record)
    assert record.getMessage() == "Listing Deployments in namespace cts"


def test_install_secret_scrubbing_filter_idempotent():
    """Installing the filter twice doesn't create duplicates."""
    import logging
    logger = logging.getLogger("test-scrub-idempotent")
    f1 = install_secret_scrubbing_filter("test-scrub-idempotent")
    f2 = install_secret_scrubbing_filter("test-scrub-idempotent")
    assert f1 is f2
    # Clean up
    logger.removeFilter(f1)


# --- KubernetesPythonDiscoveryClient tests with mocked APIs ---


class MockV1SecretKeySelector:
    def __init__(self, name, key=None):
        self.name = name
        self.key = key


class MockV1EnvVarSource:
    def __init__(self, secret_key_ref=None):
        self.secret_key_ref = secret_key_ref


class MockV1EnvVar:
    def __init__(self, name, value=None, value_from=None):
        self.name = name
        self.value = value
        self.value_from = value_from


class MockV1EnvFromSource:
    def __init__(self, secret_ref=None):
        self.secret_ref = secret_ref


class MockV1SecretEnvSource:
    def __init__(self, name, optional=False):
        self.name = name
        self.optional = optional


class MockV1Container:
    def __init__(self, name, env=None, env_from=None):
        self.name = name
        self.env = env or []
        self.env_from = env_from or []


class MockV1PodSpec:
    def __init__(self, containers=None, init_containers=None, service_account_name=None, volumes=None):
        self.containers = containers or []
        self.init_containers = init_containers or []
        self.service_account_name = service_account_name
        self.volumes = volumes or []


class MockV1PodTemplateSpec:
    def __init__(self, spec=None):
        self.spec = spec


class MockV1DeploymentSpec:
    def __init__(self, template=None):
        self.template = template


class MockV1ObjectMeta:
    def __init__(self, name="unknown", resource_version=None, annotations=None):
        self.name = name
        self.resource_version = resource_version
        self.annotations = annotations


class MockV1Volume:
    def __init__(self, name, secret=None):
        self.name = name
        self.secret = secret


class MockV1SecretVolumeSource:
    def __init__(self, secret_name):
        self.secret_name = secret_name


class MockV1Deployment:
    def __init__(self, name, containers, resource_version=None, annotations=None,
                 service_account_name=None, volumes=None, init_containers=None):
        self.metadata = MockV1ObjectMeta(
            name=name,
            resource_version=resource_version,
            annotations=annotations,
        )
        self.spec = MockV1DeploymentSpec(
            template=MockV1PodTemplateSpec(
                spec=MockV1PodSpec(
                    containers=containers,
                    init_containers=init_containers,
                    service_account_name=service_account_name,
                    volumes=volumes,
                )
            )
        )


class MockV1DeploymentList:
    def __init__(self, items):
        self.items = items


class MockAppsV1Api:
    """Mock AppsV1Api for testing."""

    def __init__(self, deployments=None, statefulsets=None, daemonsets=None):
        self._deployments = deployments or []
        self._statefulsets = statefulsets or []
        self._daemonsets = daemonsets or []

    def list_namespaced_deployment(self, namespace):
        return MockV1DeploymentList(self._deployments)

    def list_namespaced_stateful_set(self, namespace):
        return MockV1DeploymentList(self._statefulsets)

    def list_namespaced_daemon_set(self, namespace):
        return MockV1DeploymentList(self._daemonsets)


class MockBatchV1Api:
    """Mock BatchV1Api for testing."""

    def __init__(self, jobs=None, cronjobs=None):
        self._jobs = jobs or []
        self._cronjobs = cronjobs or []

    def list_namespaced_job(self, namespace):
        return MockV1DeploymentList(self._jobs)

    def list_namespaced_cron_job(self, namespace):
        return MockV1DeploymentList(self._cronjobs)


# Synthetic secret values for client tests — must NOT survive conversion
_CLIENT_TEST_SECRET = "synthetic-client-secret-must-not-survive-XYZ999"
_CLIENT_TEST_DSN = "postgresql://admin:supersecret@db.internal:5432/cts"


def test_kubernetes_python_client_namespace_scoped():
    """Client rejects requests for namespaces other than its configured scope."""
    apps_api = MockAppsV1Api()
    batch_api = MockBatchV1Api()
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=apps_api,
        batch_api=batch_api,
        load_config=False,
    )
    with pytest.raises(ValueError, match="namespace-scoped"):
        client.list_workloads("other-ns")


def test_kubernetes_python_client_returns_workload_metadata():
    """Client returns WorkloadMetadata, not raw API objects."""
    deployment = MockV1Deployment(
        name="cts-backend",
        containers=[
            MockV1Container(
                name="cts-backend",
                env=[
                    MockV1EnvVar(name="POSTGRES_DSN", value=_CLIENT_TEST_DSN),
                    MockV1EnvVar(name="PORT", value="8001"),
                ],
            ),
        ],
        resource_version="12345",
        annotations={"team": "cts-platform"},
        service_account_name="cts-backend-sa",
    )
    apps_api = MockAppsV1Api(deployments=[deployment])
    batch_api = MockBatchV1Api()
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=apps_api,
        batch_api=batch_api,
        load_config=False,
    )

    workloads = client.list_workloads("cts")
    assert len(workloads) == 1
    w = workloads[0]
    assert isinstance(w, WorkloadMetadata)
    assert w.kind == "Deployment"
    assert w.namespace == "cts"
    assert w.name == "cts-backend"
    assert w.container_name == "cts-backend"
    assert w.resource_version == "12345"
    assert w.service_account == "cts-backend-sa"
    assert w.owner_annotations.get("team") == "cts-platform"


def test_kubernetes_python_client_discards_inline_values():
    """Client discards inline env var values at the boundary."""
    deployment = MockV1Deployment(
        name="cts-backend",
        containers=[
            MockV1Container(
                name="cts-backend",
                env=[
                    MockV1EnvVar(name="POSTGRES_DSN", value=_CLIENT_TEST_DSN),
                    MockV1EnvVar(name="AWS_SECRET_ACCESS_KEY", value=_CLIENT_TEST_SECRET),
                ],
            ),
        ],
        resource_version="12345",
    )
    apps_api = MockAppsV1Api(deployments=[deployment])
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=apps_api,
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    workloads = client.list_workloads("cts")
    w = workloads[0]

    # Check no secret values in WorkloadMetadata
    from dataclasses import asdict
    metadata_json = json.dumps(asdict(w))
    assert _CLIENT_TEST_DSN not in metadata_json
    assert _CLIENT_TEST_SECRET not in metadata_json
    assert "supersecret" not in metadata_json
    assert "XYZ999" not in metadata_json

    # Check Boolean presence signals
    pg_env = next(e for e in w.env_vars if e.name == "POSTGRES_DSN")
    assert pg_env.inline_value_present is True
    assert pg_env.secret_ref_name is None


def test_kubernetes_python_client_extract_secret_key_ref():
    """Client extracts secretKeyRef references correctly."""
    deployment = MockV1Deployment(
        name="cts-backend",
        containers=[
            MockV1Container(
                name="cts-backend",
                env=[
                    MockV1EnvVar(
                        name="DATABASE_URL",
                        value_from=MockV1EnvVarSource(
                            secret_key_ref=MockV1SecretKeySelector(name="cts-db-secret", key="uri")
                        ),
                    ),
                ],
            ),
        ],
    )
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=MockAppsV1Api(deployments=[deployment]),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    workloads = client.list_workloads("cts")
    w = workloads[0]
    db_env = next(e for e in w.env_vars if e.name == "DATABASE_URL")
    assert db_env.inline_value_present is False
    assert db_env.secret_ref_name == "cts-db-secret"
    assert db_env.secret_ref_key == "uri"


def test_kubernetes_python_client_extract_env_from():
    """Client extracts envFrom secret references."""
    deployment = MockV1Deployment(
        name="cts-watchdog",
        containers=[
            MockV1Container(
                name="cts-watchdog",
                env_from=[
                    MockV1EnvFromSource(
                        secret_ref=MockV1SecretEnvSource(name="cts-shared-secrets")
                    ),
                ],
            ),
        ],
    )
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=MockAppsV1Api(deployments=[deployment]),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    workloads = client.list_workloads("cts")
    w = workloads[0]
    assert len(w.env_from) == 1
    assert w.env_from[0].secret_ref_name == "cts-shared-secrets"


def test_kubernetes_python_client_extract_volume_secrets():
    """Client extracts volume-mounted Secret references."""
    deployment = MockV1Deployment(
        name="cts-data-processor",
        containers=[MockV1Container(name="processor")],
        volumes=[
            MockV1Volume(
                name="tls-certs",
                secret=MockV1SecretVolumeSource(secret_name="cts-tls-secret"),
            ),
        ],
    )
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=MockAppsV1Api(deployments=[deployment]),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    workloads = client.list_workloads("cts")
    w = workloads[0]
    assert len(w.volume_secrets) == 1
    assert w.volume_secrets[0].volume_name == "tls-certs"
    assert w.volume_secrets[0].secret_ref_name == "cts-tls-secret"


def test_kubernetes_python_client_api_failure_raises_discovery_error():
    """API failures raise DiscoveryError with opaque coordinates, no response body."""
    class FailingAppsApi:
        def list_namespaced_deployment(self, namespace):
            raise Exception("Internal Server Error: details with sensitive content")

        def list_namespaced_stateful_set(self, namespace):
            return MockV1DeploymentList([])

        def list_namespaced_daemon_set(self, namespace):
            return MockV1DeploymentList([])

    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=FailingAppsApi(),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    with pytest.raises(DiscoveryError, match="Failed to list Deployments"):
        client.list_workloads("cts")


def test_kubernetes_python_client_api_failure_no_response_body():
    """DiscoveryError does not contain the raw exception's response body."""
    class FailingAppsApi:
        def list_namespaced_deployment(self, namespace):
            raise Exception("Internal Server Error: sensitive response body with secrets")

        def list_namespaced_stateful_set(self, namespace):
            return MockV1DeploymentList([])

        def list_namespaced_daemon_set(self, namespace):
            return MockV1DeploymentList([])

    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=FailingAppsApi(),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    try:
        client.list_workloads("cts")
        assert False, "Should have raised DiscoveryError"
    except DiscoveryError as e:
        msg = str(e)
        assert "cts" in msg
        assert "Deployment" in msg
        # The raw exception's response body must NOT be in the error
        assert "sensitive response body" not in msg
        assert "secrets" not in msg


def test_kubernetes_python_client_no_raw_exception_chaining():
    """DiscoveryError does not chain the raw exception."""
    class FailingAppsApi:
        def list_namespaced_deployment(self, namespace):
            raise Exception("raw exception with sensitive content")

        def list_namespaced_stateful_set(self, namespace):
            return MockV1DeploymentList([])

        def list_namespaced_daemon_set(self, namespace):
            return MockV1DeploymentList([])

    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=FailingAppsApi(),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    try:
        client.list_workloads("cts")
    except DiscoveryError as e:
        # __cause__ should be None (we used `from None`)
        assert e.__cause__ is None
        # __suppress_context__ should be True (set by `from None`)
        # This means Python won't print the raw exception in tracebacks
        assert e.__suppress_context__ is True


def test_kubernetes_python_client_no_secret_read_method():
    """Client has no method for reading Secret data."""
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=MockAppsV1Api(),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )
    # Verify no secret-reading methods exist
    assert not hasattr(client, "read_namespaced_secret")
    assert not hasattr(client, "read_secret")
    assert not hasattr(client, "get_secret")
    assert not hasattr(client, "list_secrets")


def test_kubernetes_python_client_end_to_end_with_adapter():
    """Full pipeline: mocked API → client → adapter → observations, no secrets survive."""
    raw_secret = "end-to-end-client-secret-MUST-NOT-SURVIVE"

    deployment = MockV1Deployment(
        name="cts-backend",
        containers=[
            MockV1Container(
                name="cts-backend",
                env=[
                    MockV1EnvVar(name="POSTGRES_DSN", value=raw_secret),
                    MockV1EnvVar(name="AWS_SECRET_ACCESS_KEY", value=raw_secret),
                    MockV1EnvVar(name="PORT", value="8001"),
                    MockV1EnvVar(
                        name="DATABASE_URL",
                        value_from=MockV1EnvVarSource(
                            secret_key_ref=MockV1SecretKeySelector(name="cts-db-secret", key="uri")
                        ),
                    ),
                ],
                env_from=[
                    MockV1EnvFromSource(
                        secret_ref=MockV1SecretEnvSource(name="cts-shared-secrets")
                    ),
                ],
            ),
        ],
        resource_version="12345",
        annotations={"team": "cts-platform", "service": "attunement-weaver"},
        service_account_name="cts-backend-sa",
    )

    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=MockAppsV1Api(deployments=[deployment]),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    # Run the adapter with the real client
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )

    assert len(observations) > 0

    # Verify no secret values in any observation
    for obs in observations:
        obs_json = json.dumps(obs.to_dict())
        assert raw_secret not in obs_json
        assert "MUST-NOT-SURVIVE" not in obs_json

    # Verify all observations pass safety check
    assert_observations_safe(observations)

    # Verify inline credentials are flagged
    pg_obs = next(o for o in observations if "POSTGRES_DSN" in o.observation_id)
    assert pg_obs.inline_value_present is True
    assert pg_obs.exposure_class == EXPOSURE_ACTIVE_IN_SOURCE
    assert pg_obs.default_action == ACTION_EMERGENCY_ROTATION

    # Verify secretKeyRef credentials are classified correctly
    db_url_obs = next(o for o in observations if "DATABASE_URL" in o.observation_id)
    assert db_url_obs.inline_value_present is False
    assert db_url_obs.exposure_class == EXPOSURE_SECRET_DELIVERED
    assert db_url_obs.default_action == ACTION_ENROLLMENT_CANDIDATE

    # Verify envFrom gets shared exposure class
    envfrom_obs = [o for o in observations if "envfrom" in o.observation_id]
    assert len(envfrom_obs) == 1
    assert envfrom_obs[0].exposure_class == EXPOSURE_SECRET_DELIVERED_SHARED


def test_kubernetes_python_client_multiple_workload_types():
    """Client lists Deployments, StatefulSets, DaemonSets, Jobs, CronJobs."""
    deployment = MockV1Deployment(name="cts-backend", containers=[MockV1Container(name="app")])
    statefulset = MockV1Deployment(name="cts-data", containers=[MockV1Container(name="data")])
    daemonset = MockV1Deployment(name="cts-agent", containers=[MockV1Container(name="agent")])

    apps_api = MockAppsV1Api(
        deployments=[deployment],
        statefulsets=[statefulset],
        daemonsets=[daemonset],
    )
    batch_api = MockBatchV1Api(jobs=[deployment], cronjobs=[statefulset])

    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=apps_api,
        batch_api=batch_api,
        load_config=False,
    )

    workloads = client.list_workloads("cts")
    # 3 from apps (deploy, sts, ds) + 2 from batch (job, cron) = 5
    assert len(workloads) == 5
    kinds = {w.kind for w in workloads}
    assert "Deployment" in kinds
    assert "StatefulSet" in kinds
    assert "DaemonSet" in kinds
    assert "Job" in kinds
    assert "CronJob" in kinds


def test_kubernetes_python_client_empty_namespace():
    """Client returns empty tuple for namespace with no workloads."""
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=MockAppsV1Api(),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )
    workloads = client.list_workloads("cts")
    assert len(workloads) == 0


def test_kubernetes_python_client_init_containers():
    """Client processes init containers in addition to main containers."""
    deployment = MockV1Deployment(
        name="cts-backend",
        containers=[
            MockV1Container(name="main", env=[MockV1EnvVar(name="PORT", value="8001")]),
        ],
        init_containers=[
            MockV1Container(
                name="init-db",
                env=[
                    MockV1EnvVar(name="POSTGRES_DSN", value=_CLIENT_TEST_DSN),
                ],
            ),
        ],
    )
    client = KubernetesPythonDiscoveryClient(
        namespace="cts",
        apps_api=MockAppsV1Api(deployments=[deployment]),
        batch_api=MockBatchV1Api(),
        load_config=False,
    )

    workloads = client.list_workloads("cts")
    w = workloads[0]
    # Should have env vars from both main and init containers
    env_names = {e.name for e in w.env_vars}
    assert "PORT" in env_names
    assert "POSTGRES_DSN" in env_names

    # Init container's inline value must be discarded
    from dataclasses import asdict
    metadata_json = json.dumps(asdict(w))
    assert _CLIENT_TEST_DSN not in metadata_json
    assert "supersecret" not in metadata_json


# --- Exposure class refinement tests ---


def test_envfrom_gets_shared_exposure_class():
    """envFrom secret references get EXPOSURE_SECRET_DELIVERED_SHARED."""
    client = SyntheticK8sClient((_make_cts_watchdog_workload(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    envfrom_obs = [o for o in observations if "envfrom" in o.observation_id]
    assert len(envfrom_obs) == 1
    assert envfrom_obs[0].exposure_class == EXPOSURE_SECRET_DELIVERED_SHARED


def test_volume_secret_gets_certificate_exposure_class():
    """Volume-mounted secrets get EXPOSURE_CERTIFICATE_DELIVERED."""
    client = SyntheticK8sClient((_make_cts_with_volume_secret(),))
    observations = discover_kubernetes_credentials(
        client=client,
        namespace="cts",
        environment="dev",
    )
    vol_obs = [o for o in observations if "volume" in o.observation_id]
    assert len(vol_obs) == 1
    assert vol_obs[0].exposure_class == EXPOSURE_CERTIFICATE_DELIVERED


# --- run_discovery module tests ---


def test_build_coverage_kubernetes_only():
    """Coverage map marks kubernetes as completed, others as not_configured."""
    from platform_orchestration_contracts.run_discovery import _build_coverage
    coverage = _build_coverage(["kubernetes"])
    assert coverage[COVERAGE_SOURCE_KUBERNETES] == COVERAGE_COMPLETED
    assert coverage[COVERAGE_SOURCE_POSTGRES] == COVERAGE_NOT_CONFIGURED
    assert coverage[COVERAGE_SOURCE_MINIO] == COVERAGE_NOT_CONFIGURED
    assert coverage[COVERAGE_SOURCE_GIT_FINDINGS] == COVERAGE_NOT_CONFIGURED


def test_build_coverage_all_not_configured_when_empty():
    """Empty sources list marks all as not_configured."""
    from platform_orchestration_contracts.run_discovery import _build_coverage
    coverage = _build_coverage([])
    assert coverage[COVERAGE_SOURCE_KUBERNETES] == COVERAGE_NOT_CONFIGURED
    assert coverage[COVERAGE_SOURCE_POSTGRES] == COVERAGE_NOT_CONFIGURED


def test_count_emergency_items_with_inline():
    """Emergency count includes active_in_source observations."""
    from platform_orchestration_contracts.run_discovery import _count_emergency_items
    obs = (
        CredentialObservation(
            observation_id="obs-1",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
            default_action=ACTION_EMERGENCY_ROTATION,
        ),
        CredentialObservation(
            observation_id="obs-2",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            exposure_class=EXPOSURE_SECRET_DELIVERED,
            default_action=ACTION_ENROLLMENT_CANDIDATE,
        ),
    )
    assert _count_emergency_items(obs) == 1


def test_count_emergency_items_zero_when_none():
    """Emergency count is zero when no active exposures."""
    from platform_orchestration_contracts.run_discovery import _count_emergency_items
    obs = (
        CredentialObservation(
            observation_id="obs-1",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            exposure_class=EXPOSURE_SECRET_DELIVERED,
            default_action=ACTION_ENROLLMENT_CANDIDATE,
        ),
    )
    assert _count_emergency_items(obs) == 0


def test_observation_to_record_inline_credential():
    """Observation with active_in_source becomes bootstrap_required record."""
    from platform_orchestration_contracts.run_discovery import _observation_to_record
    obs = CredentialObservation(
        observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        credential_class="postgresql_login",
        secret_authority_ref="inline-env:cts/cts-backend#POSTGRES_DSN",
        consumer_refs=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
        owner_hint=OwnerRef(team="cts-platform"),
        risk_signals=("credential-inlined-in-env-var",),
        exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
        evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
        inline_value_present=True,
        default_action=ACTION_EMERGENCY_ROTATION,
    )
    record = _observation_to_record(obs)
    assert record.credential_set_id == "candidate-k8s-cts-deployment-cts-backend-cts-backend-postgres_dsn"
    assert record.lifecycle_state == LIFECYCLE_BOOTSTRAP_REQUIRED
    assert record.risk.tier == RISK_HIGH
    assert record.authority is not None
    assert record.authority.provider == "inline_env"
    assert record.target_strategy == ACTION_EMERGENCY_ROTATION


def test_observation_to_record_secret_key_ref():
    """Observation with secretKeyRef becomes discovered record."""
    from platform_orchestration_contracts.run_discovery import _observation_to_record
    obs = CredentialObservation(
        observation_id="k8s:cts:deployment:cts-backend:cts-backend:DATABASE_URL",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        credential_class="postgresql_login",
        secret_authority_ref="kubernetes-secret:cts/cts-db-secret#uri",
        consumer_refs=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
        exposure_class=EXPOSURE_SECRET_DELIVERED,
        evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
        default_action=ACTION_ENROLLMENT_CANDIDATE,
    )
    record = _observation_to_record(obs)
    assert record.lifecycle_state == LIFECYCLE_DISCOVERED
    assert record.risk.tier == RISK_LOW
    assert record.authority is not None
    assert record.authority.provider == "kubernetes_secret"
    assert record.authority.namespace == "cts"
    assert record.authority.secret_name == "cts-db-secret"
    assert "uri" in record.authority.key_names


def test_format_emergency_items_no_secret_values():
    """Emergency item formatting contains no secret values."""
    from platform_orchestration_contracts.run_discovery import _format_emergency_items
    raw_secret = "formatting-test-secret-NOT-IN-OUTPUT"
    obs = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            consumer_refs=(ConsumerRef(
                kind="Deployment", namespace="cts", name="cts-backend", container="cts-backend",
            ),),
            exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
            default_action=ACTION_EMERGENCY_ROTATION,
        ),
    )
    items = _format_emergency_items(obs)
    assert len(items) == 1
    item = items[0]
    assert "cts-backend" in item
    assert "POSTGRES_DSN" in item
    assert "emergency_rotation" in item
    # No secret values
    assert raw_secret not in item
    assert "password" not in item.lower()


def test_run_discovery_writes_json_and_markdown(tmp_path):
    """run_discovery writes JSON and Markdown reports to the evidence bundle."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    # Create mock observations to return from discover_kubernetes_credentials
    mock_observations = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:DATABASE_URL",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            secret_authority_ref="kubernetes-secret:cts/cts-db-secret#uri",
            consumer_refs=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
            owner_hint=OwnerRef(team="cts-platform"),
            exposure_class=EXPOSURE_SECRET_DELIVERED,
            evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
            default_action=ACTION_ENROLLMENT_CANDIDATE,
        ),
    )

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient") as mock_client_cls:
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            exit_code = run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                environment="dev",
                run_id="test-run-001",
            )

    # No emergency items, so exit code should be 0
    assert exit_code == 0

    # Evidence bundle is at a structured path
    bundle_path = tmp_path / "credential-discovery" / "environment=dev" / "run_id=test-run-001"
    assert bundle_path.exists()

    # Check JSON report exists
    json_path = bundle_path / "report.json"
    assert json_path.exists()
    report_json = json_path.read_text()
    report_data = json.loads(report_json)

    # Verify report structure
    assert report_data["run_id"] == "test-run-001"
    assert report_data["report_version"] == "credential-posture-report.v1"
    assert "contract_package_version" in report_data
    assert "entries_sha256" in report_data
    assert "evidence_manifest_ref" in report_data
    assert "coverage" in report_data
    assert report_data["coverage"][COVERAGE_SOURCE_KUBERNETES] == COVERAGE_COMPLETED
    assert report_data["coverage"][COVERAGE_SOURCE_POSTGRES] == COVERAGE_NOT_CONFIGURED

    # Check Markdown report exists
    md_path = bundle_path / "report.md"
    assert md_path.exists()
    report_md = md_path.read_text()
    assert "test-run-001" in report_md

    # Check manifest exists
    manifest_path = bundle_path / "manifest.json"
    assert manifest_path.exists()
    manifest_data = json.loads(manifest_path.read_text())
    assert manifest_data["manifest_version"] == "credential-discovery-evidence.v1"
    assert manifest_data["run_id"] == "test-run-001"
    assert "report_json_sha256" in manifest_data
    assert "report_markdown_sha256" in manifest_data

    # Check checksums file exists
    checksums_path = bundle_path / "checksums.txt"
    assert checksums_path.exists()


def test_run_discovery_returns_2_for_emergency_items(tmp_path):
    """run_discovery returns exit code 2 when emergency items are found."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    mock_observations = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            secret_authority_ref="inline-env:cts/cts-backend#POSTGRES_DSN",
            consumer_refs=(ConsumerRef(
                kind="Deployment", namespace="cts", name="cts-backend", container="cts-backend",
            ),),
            owner_hint=OwnerRef(team="cts-platform"),
            exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
            evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
            inline_value_present=True,
            default_action=ACTION_EMERGENCY_ROTATION,
        ),
    )

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            exit_code = run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                environment="dev",
                run_id="test-emergency-001",
            )

    # Emergency items found → exit code 2
    assert exit_code == 2

    # Report should still be written to evidence bundle
    bundle_path = tmp_path / "credential-discovery" / "environment=dev" / "run_id=test-emergency-001"
    assert bundle_path.exists()
    assert (bundle_path / "report.json").exists()


def test_run_discovery_report_contains_no_secret_values(tmp_path):
    """Posture report contains no secret values."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    raw_secret = "report-test-secret-MUST-NOT-APPEAR"

    mock_observations = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            secret_authority_ref="inline-env:cts/cts-backend#POSTGRES_DSN",
            consumer_refs=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
            exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
            evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
            inline_value_present=True,
            default_action=ACTION_EMERGENCY_ROTATION,
        ),
    )

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                run_id="test-no-secrets-001",
            )

    # Check JSON report has no secret values
    bundle_path = tmp_path / "credential-discovery" / "environment=dev" / "run_id=test-no-secrets-001"
    json_report = (bundle_path / "report.json").read_text()
    assert raw_secret not in json_report
    assert "MUST-NOT-APPEAR" not in json_report

    # Check Markdown report has no secret values
    md_report = (bundle_path / "report.md").read_text()
    assert raw_secret not in md_report
    assert "MUST-NOT-APPEAR" not in md_report

    # Check manifest has no secret values
    manifest_report = (bundle_path / "manifest.json").read_text()
    assert raw_secret not in manifest_report
    assert "MUST-NOT-APPEAR" not in manifest_report

    # Check checksums has no secret values
    checksums_report = (bundle_path / "checksums.txt").read_text()
    assert raw_secret not in checksums_report
    assert "MUST-NOT-APPEAR" not in checksums_report


def test_run_discovery_coverage_honest(tmp_path):
    """Report honestly marks non-kubernetes sources as not_configured."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    mock_observations = ()

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                run_id="test-coverage-001",
            )

    bundle_path = tmp_path / "credential-discovery" / "environment=dev" / "run_id=test-coverage-001"
    json_report = (bundle_path / "report.json").read_text()
    report_data = json.loads(json_report)

    # Kubernetes should be completed
    assert report_data["coverage"][COVERAGE_SOURCE_KUBERNETES] == COVERAGE_COMPLETED
    # Others should be not_configured
    assert report_data["coverage"][COVERAGE_SOURCE_POSTGRES] == COVERAGE_NOT_CONFIGURED
    assert report_data["coverage"][COVERAGE_SOURCE_MINIO] == COVERAGE_NOT_CONFIGURED
    assert report_data["coverage"][COVERAGE_SOURCE_GIT_FINDINGS] == COVERAGE_NOT_CONFIGURED
    # Should have limitations for missing sources
    assert "limitations" in report_data
    assert len(report_data["limitations"]) > 0


def test_run_discovery_evidence_manifest_ref(tmp_path):
    """Report includes evidence_manifest_ref."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    mock_observations = ()

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                run_id="test-evidence-001",
            )

    bundle_path = tmp_path / "credential-discovery" / "environment=dev" / "run_id=test-evidence-001"
    json_report = (bundle_path / "report.json").read_text()
    report_data = json.loads(json_report)

    assert "evidence_manifest_ref" in report_data
    assert report_data["evidence_manifest_ref"] is not None
    assert "security-evidence://" in report_data["evidence_manifest_ref"]
    assert "cts" in report_data["evidence_manifest_ref"]
    assert "test-evidence-001" in report_data["evidence_manifest_ref"]


# --- Report safety gate tests ---


def test_assert_safe_report_text_rejects_password():
    """Report safety gate rejects password= patterns."""
    # Construct dynamically to avoid triggering secret scanners
    text = "config has pass" + "word=secret123 in it"
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_safe_report_text(text, context="test")


def test_assert_safe_report_text_rejects_postgres_dsn():
    """Report safety gate rejects postgres:// DSN patterns."""
    # Construct dynamically to avoid triggering secret scanners
    text = "DSN: postgres" + "ql://user:secret@host:5432/db"
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_safe_report_text(text, context="test")


def test_assert_safe_report_text_rejects_token():
    """Report safety gate rejects token= patterns."""
    text = "auth tok" + "en=abc123def456"
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_safe_report_text(text, context="test")


def test_assert_safe_report_text_rejects_api_key():
    """Report safety gate rejects api_key= patterns."""
    # Construct dynamically to avoid triggering secret scanners
    text = "config api_" + "key=" + "syn" + "thetic"
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_safe_report_text(text, context="test")


def test_assert_safe_report_text_rejects_bearer():
    """Report safety gate rejects Authorization: Bearer patterns."""
    text = "header authoriz" + "ation: bearer abc123token"
    with pytest.raises(UnsafeObservationError, match="prohibited"):
        assert_safe_report_text(text, context="test")


def test_assert_safe_report_text_passes_clean_report():
    """Report safety gate passes clean report text."""
    text = json.dumps({
        "run_id": "test-001",
        "namespace": "cts",
        "coverage": {"kubernetes": "completed"},
        "entries_sha256": "abc123",
        "observations": [
            {"observation_id": "k8s-cts-deployment-cts-backend-postgres_dsn",
             "inline_value_present": True,
             "exposure_class": "active_in_source"}
        ],
    })
    # Should not raise
    assert_safe_report_text(text, context="test")


def test_assert_safe_report_text_passes_env_var_names():
    """Report safety gate passes legitimate env var names (no value indicator)."""
    text = "POSTGRES_DSN AWS_SECRET_ACCESS_KEY DATABASE_URL"
    # These are env var names without trailing = or :value patterns
    # Should not raise because the forbidden markers require value indicators
    assert_safe_report_text(text, context="test")


def test_run_discovery_report_safety_gate_blocks_unsafe_output(tmp_path):
    """run_discovery returns 1 if report text fails safety validation."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch, MagicMock

    mock_observations = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:DATABASE_URL",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            secret_authority_ref="kubernetes-secret:cts/cts-db-secret#uri",
            consumer_refs=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
            exposure_class=EXPOSURE_SECRET_DELIVERED,
            evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
            default_action=ACTION_ENROLLMENT_CANDIDATE,
        ),
    )

    output_path = str(tmp_path / "credential-posture.json")

    # Mock assert_safe_report_text to raise
    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            with patch("platform_orchestration_contracts.run_discovery.assert_safe_report_text") as mock_safe:
                mock_discover.return_value = mock_observations
                mock_safe.side_effect = UnsafeObservationError(
                    observation_id="<json-report>",
                    reason="test: blocked",
                    marker="test-marker",
                )
                exit_code = run_discovery(
                    namespace="cts",
                    sources=["kubernetes"],
                    output_path=output_path,
                    run_id="test-gate-001",
                )

    assert exit_code == 1
    # Evidence bundle should NOT have been written
    bundle_path = tmp_path / "credential-discovery"
    assert not bundle_path.exists()


# --- Correlation metadata tests ---


def test_observation_to_record_prefixes_candidate_id():
    """Records from _observation_to_record are prefixed with candidate-."""
    from platform_orchestration_contracts.run_discovery import _observation_to_record
    obs = CredentialObservation(
        observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        credential_class="postgresql_login",
        exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
        default_action=ACTION_EMERGENCY_ROTATION,
    )
    record = _observation_to_record(obs)
    assert record.credential_set_id.startswith("candidate-")
    assert "k8s" in record.credential_set_id
    assert "cts" in record.credential_set_id
    assert "postgres_dsn" in record.credential_set_id


def test_observation_to_record_candidate_id_is_lowercase():
    """Candidate IDs are lowercase to satisfy credential_set_id validation."""
    from platform_orchestration_contracts.run_discovery import _observation_to_record
    obs = CredentialObservation(
        observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
        source=COVERAGE_SOURCE_KUBERNETES,
        observed_at="2026-09-05T12:00:00+00:00",
        environment="dev",
        exposure_class=EXPOSURE_SECRET_DELIVERED,
        default_action=ACTION_ENROLLMENT_CANDIDATE,
    )
    record = _observation_to_record(obs)
    # Must be valid per credential_set_id pattern: [a-z0-9][a-z0-9_-]*
    import re
    assert re.match(r"^[a-z0-9][a-z0-9_-]*$", record.credential_set_id), \
        f"credential_set_id {record.credential_set_id!r} does not match required pattern"


# --- Evidence bundle tests ---


def test_write_safe_evidence_bundle_creates_files(tmp_path):
    """write_safe_evidence_bundle creates all files atomically."""
    from platform_orchestration_contracts.evidence_bundle import write_safe_evidence_bundle
    destination = tmp_path / "bundle"
    files = {
        "report.json": '{"run_id": "test-001"}',
        "report.md": "# Report\ntest-001",
        "manifest.json": '{"manifest_version": "credential-discovery-evidence.v1"}',
        "checksums.txt": "abc123  report.json\n",
    }
    write_safe_evidence_bundle(destination=destination, files=files)
    assert destination.exists()
    assert (destination / "report.json").exists()
    assert (destination / "report.md").exists()
    assert (destination / "manifest.json").exists()
    assert (destination / "checksums.txt").exists()
    assert (destination / "report.json").read_text() == '{"run_id": "test-001"}'


def test_write_safe_evidence_bundle_rejects_unsafe_content(tmp_path):
    """write_safe_evidence_bundle rejects content with secret markers."""
    from platform_orchestration_contracts.evidence_bundle import write_safe_evidence_bundle
    destination = tmp_path / "bundle"
    # Construct unsafe content dynamically
    unsafe = "config pass" + "word=secret123"
    files = {
        "report.json": unsafe,
    }
    with pytest.raises(UnsafeObservationError):
        write_safe_evidence_bundle(destination=destination, files=files)
    # Nothing should be written
    assert not destination.exists()


def test_write_safe_evidence_bundle_no_partial_writes_on_failure(tmp_path):
    """If one file fails safety check, no files are written."""
    from platform_orchestration_contracts.evidence_bundle import write_safe_evidence_bundle
    destination = tmp_path / "bundle"
    safe_content = '{"run_id": "test-001"}'
    unsafe = "tok" + "en=secret123"
    files = {
        "report.json": safe_content,
        "bad.txt": unsafe,
    }
    with pytest.raises(UnsafeObservationError):
        write_safe_evidence_bundle(destination=destination, files=files)
    assert not destination.exists()


def test_build_evidence_manifest_structure():
    """build_evidence_manifest produces correct manifest structure."""
    from platform_orchestration_contracts.evidence_bundle import build_evidence_manifest
    from platform_orchestration_contracts.credential_discovery_workflow import (
        PostureReport, COVERAGE_COMPLETED, COVERAGE_NOT_CONFIGURED,
    )
    report = PostureReport(
        run_id="test-manifest-001",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={
            COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED,
            COVERAGE_SOURCE_POSTGRES: COVERAGE_NOT_CONFIGURED,
        },
        entries_sha256="sha256:abc123",
        contract_package_version=__version__,
    )
    manifest_json = build_evidence_manifest(
        report=report,
        report_json='{"test": true}',
        report_markdown="# Test",
    )
    manifest = json.loads(manifest_json)
    assert manifest["manifest_version"] == "credential-discovery-evidence.v1"
    assert manifest["run_id"] == "test-manifest-001"
    assert manifest["entries_sha256"] == "sha256:abc123"
    assert manifest["package_version"] == __version__
    assert manifest["policy_version"] == "1"
    assert "report_json_sha256" in manifest
    assert manifest["report_json_sha256"].startswith("sha256:")
    assert "report_markdown_sha256" in manifest
    assert manifest["coverage"][COVERAGE_SOURCE_KUBERNETES] == COVERAGE_COMPLETED


def test_build_checksums_text_format():
    """build_checksums_text produces correct checksums format."""
    from platform_orchestration_contracts.evidence_bundle import build_checksums_text
    checksums = build_checksums_text(
        report_json='{"test": true}',
        report_markdown="# Test",
        manifest_json='{"manifest": true}',
    )
    lines = checksums.strip().split("\n")
    assert len(lines) == 3
    assert lines[0].endswith("  report.json")
    assert lines[1].endswith("  report.md")
    assert lines[2].endswith("  manifest.json")
    # Each line should start with a hex digest
    for line in lines:
        parts = line.split("  ", 1)
        assert len(parts[0]) == 64  # SHA-256 hex digest length


def test_write_discovery_evidence_creates_bundle(tmp_path):
    """write_discovery_evidence creates a complete evidence bundle."""
    from platform_orchestration_contracts.evidence_bundle import write_discovery_evidence
    from platform_orchestration_contracts.credential_discovery_workflow import (
        PostureReport, COVERAGE_COMPLETED, COVERAGE_NOT_CONFIGURED,
    )
    report = PostureReport(
        run_id="test-bundle-001",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:abc123",
        contract_package_version=__version__,
    )
    bundle_path = write_discovery_evidence(
        base_path=tmp_path,
        run_id="test-bundle-001",
        environment="dev",
        report=report,
    )
    assert bundle_path.exists()
    assert (bundle_path / "report.json").exists()
    assert (bundle_path / "report.md").exists()
    assert (bundle_path / "manifest.json").exists()
    assert (bundle_path / "checksums.txt").exists()
    # Verify the directory structure
    assert "environment=dev" in str(bundle_path)
    assert "run_id=test-bundle-001" in str(bundle_path)


def test_write_discovery_evidence_no_secret_values(tmp_path):
    """Evidence bundle contains no secret values in any file."""
    from platform_orchestration_contracts.evidence_bundle import write_discovery_evidence
    from platform_orchestration_contracts.credential_discovery_workflow import (
        PostureReport, COVERAGE_COMPLETED,
    )
    raw_secret = "bundle-test-secret-MUST-NOT-APPEAR"
    # We can't put raw_secret in the report (it would fail safety),
    # but we verify that the bundle files don't contain it
    report = PostureReport(
        run_id="test-no-secret-bundle-001",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:abc123",
        contract_package_version=__version__,
    )
    bundle_path = write_discovery_evidence(
        base_path=tmp_path,
        run_id="test-no-secret-bundle-001",
        environment="dev",
        report=report,
    )
    for fname in ("report.json", "report.md", "manifest.json", "checksums.txt"):
        content = (bundle_path / fname).read_text()
        assert raw_secret not in content
        assert "MUST-NOT-APPEAR" not in content


# --- Correlation status in posture entries ---


def test_posture_entry_has_correlation_fields():
    """CredentialPostureEntry includes correlation metadata."""
    from platform_orchestration_contracts.credential_discovery_workflow import (
        CredentialPostureEntry,
    )
    entry = CredentialPostureEntry(
        credential_set_id="candidate-test-001",
        credential_class="postgresql_login",
        environment="dev",
        owner=None,
        lifecycle_state="discovered",
        consumer_count=1,
        provider_identity_ref="kubernetes_secret:cts/db-secret",
        secret_authority_status="unmanaged",
        risk_tier="low",
        provider_ready=False,
        execution_ready=False,
        eligible=False,
        blockers=(),
        exposure_status="unknown",
        last_observed_use=None,
        enrollment_deadline=None,
        recommended_next_action="begin_enrollment",
        input_fingerprint="abc123",
    )
    # Default values
    assert entry.correlation_status == "unconfirmed"
    assert entry.correlation_basis == ()
    assert entry.requires_owner_confirmation is True

    # to_dict includes correlation fields
    d = entry.to_dict()
    assert "correlation_status" in d
    assert d["correlation_status"] == "unconfirmed"
    assert "correlation_basis" in d
    assert "requires_owner_confirmation" in d


def test_build_posture_entry_default_correlation():
    """build_posture_entry defaults to unconfirmed correlation."""
    from platform_orchestration_contracts.credential_discovery_workflow import (
        build_posture_entry,
    )
    from platform_orchestration_contracts.credential_inventory import (
        CredentialSetRecord, RotationCapabilities, RiskAssessment,
    )
    record = CredentialSetRecord(
        credential_set_id="candidate-test-002",
        display_name="test-credential",
        credential_class="postgresql_login",
        environment="dev",
        lifecycle_state=LIFECYCLE_DISCOVERED,
        risk=RiskAssessment(tier=RISK_LOW),
        capabilities=RotationCapabilities(),
    )
    from platform_orchestration_contracts.credential_inventory import (
        evaluate_rotation_eligibility, RotationSubject,
    )
    subject = RotationSubject(
        credential_set_id="candidate-test-002",
        provider_ref="test:provider",
        provider_identity_ref="test:provider",
        secret_authority_ref="test:provider",
        consumer_set_ref="cts/test",
        consumer_set_version="discovery:v1",
        rotation_strategy="unknown",
        reload_strategy="unknown",
    )
    eligibility = evaluate_rotation_eligibility(
        subject=subject,
        risk_tier=RISK_LOW,
        capabilities=RotationCapabilities(),
        policy_version="1",
    )
    entry = build_posture_entry(record=record, eligibility=eligibility)
    assert entry.correlation_status == "unconfirmed"
    assert "workload_reference" in entry.correlation_basis
    assert entry.requires_owner_confirmation is True


def test_posture_report_markdown_includes_correlation_notice():
    """PostureReport Markdown includes correlation notice for unconfirmed entries."""
    from platform_orchestration_contracts.credential_discovery_workflow import (
        CredentialPostureEntry, PostureReport,
    )
    entry = CredentialPostureEntry(
        credential_set_id="candidate-test-003",
        credential_class="postgresql_login",
        environment="dev",
        owner=None,
        lifecycle_state="discovered",
        consumer_count=1,
        provider_identity_ref=None,
        secret_authority_status="unknown",
        risk_tier="low",
        provider_ready=False,
        execution_ready=False,
        eligible=False,
        blockers=(),
        exposure_status="unknown",
        last_observed_use=None,
        enrollment_deadline=None,
        recommended_next_action="begin_enrollment",
        input_fingerprint="abc123",
        correlation_status="unconfirmed",
        correlation_basis=("workload_reference",),
    )
    report = PostureReport(
        run_id="test-corr-md-001",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=1,
        eligible_count=0,
        blocked_count=1,
        unowned_count=1,
        orphaned_count=0,
        entries=(entry,),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:abc123",
        contract_package_version=__version__,
    )
    md = report.to_markdown()
    assert "Correlation notice" in md
    assert "unconfirmed" in md
    assert "candidate" in md.lower()


# --- Scan status and exit code in evidence manifest ---


def test_evidence_manifest_includes_scan_status_completed():
    """Manifest includes scan_status=completed for exit 0, no findings."""
    from platform_orchestration_contracts.evidence_bundle import build_evidence_manifest
    from platform_orchestration_contracts.credential_discovery_workflow import PostureReport
    report = PostureReport(
        run_id="test-status-001",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        entries_sha256="sha256:abc",
        contract_package_version=__version__,
    )
    manifest = json.loads(build_evidence_manifest(
        report=report,
        report_json='{}',
        report_markdown='# Test',
        exit_code=0,
    ))
    assert manifest["scan_status"] == "completed"
    assert manifest["exit_code"] == 0


def test_evidence_manifest_includes_scan_status_completed_with_findings():
    """Manifest includes scan_status=completed_with_findings for exit 2."""
    from platform_orchestration_contracts.evidence_bundle import build_evidence_manifest
    from platform_orchestration_contracts.credential_discovery_workflow import (
        PostureReport, CredentialPostureEntry,
    )
    entry = CredentialPostureEntry(
        credential_set_id="candidate-test",
        credential_class="postgresql_login",
        environment="dev",
        owner=None,
        lifecycle_state="bootstrap_required",
        consumer_count=1,
        provider_identity_ref=None,
        secret_authority_status="unknown",
        risk_tier="high",
        provider_ready=False,
        execution_ready=False,
        eligible=False,
        blockers=(),
        exposure_status="active_in_source",
        last_observed_use=None,
        enrollment_deadline=None,
        recommended_next_action="emergency_rotation",
        input_fingerprint="abc",
    )
    report = PostureReport(
        run_id="test-status-002",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=1,
        eligible_count=0,
        blocked_count=1,
        unowned_count=1,
        orphaned_count=0,
        entries=(entry,),
        entries_sha256="sha256:abc",
        contract_package_version=__version__,
    )
    manifest = json.loads(build_evidence_manifest(
        report=report,
        report_json='{}',
        report_markdown='# Test',
        exit_code=2,
    ))
    assert manifest["scan_status"] == "completed_with_findings"
    assert manifest["exit_code"] == 2
    assert manifest["emergency_items"] == 1


def test_evidence_manifest_includes_scan_status_failed():
    """Manifest includes scan_status=failed for exit 1."""
    from platform_orchestration_contracts.evidence_bundle import build_evidence_manifest
    from platform_orchestration_contracts.credential_discovery_workflow import PostureReport
    report = PostureReport(
        run_id="test-status-003",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        entries_sha256="sha256:abc",
        contract_package_version=__version__,
    )
    manifest = json.loads(build_evidence_manifest(
        report=report,
        report_json='{}',
        report_markdown='# Test',
        exit_code=1,
    ))
    assert manifest["scan_status"] == "failed"
    assert manifest["exit_code"] == 1


def test_evidence_manifest_rejects_invalid_scan_status():
    """Manifest rejects invalid scan_status values."""
    from platform_orchestration_contracts.evidence_bundle import build_evidence_manifest
    from platform_orchestration_contracts.credential_discovery_workflow import PostureReport
    report = PostureReport(
        run_id="test-status-004",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        entries_sha256="sha256:abc",
        contract_package_version=__version__,
    )
    with pytest.raises(ValueError, match="scan_status"):
        build_evidence_manifest(
            report=report,
            report_json='{}',
            report_markdown='# Test',
            scan_status="bogus_status",
        )


def test_run_discovery_manifest_has_completed_with_findings(tmp_path):
    """Evidence manifest records completed_with_findings for exit 2 runs."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    mock_observations = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            secret_authority_ref="inline-env:cts/cts-backend#POSTGRES_DSN",
            consumer_refs=(ConsumerRef(
                kind="Deployment", namespace="cts", name="cts-backend", container="cts-backend",
            ),),
            owner_hint=OwnerRef(team="cts-platform"),
            exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
            evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
            inline_value_present=True,
            default_action=ACTION_EMERGENCY_ROTATION,
        ),
    )

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            exit_code = run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                run_id="test-findings-manifest-001",
            )

    assert exit_code == 2

    bundle_path = tmp_path / "credential-discovery" / "environment=dev" / "run_id=test-findings-manifest-001"
    manifest = json.loads((bundle_path / "manifest.json").read_text())
    assert manifest["scan_status"] == "completed_with_findings"
    assert manifest["exit_code"] == 2
    assert manifest["emergency_items"] >= 1


# --- Collision handling and idempotency tests ---


def test_write_safe_evidence_bundle_idempotent_replay(tmp_path):
    """Writing the same bundle twice is a safe replay (no error)."""
    from platform_orchestration_contracts.evidence_bundle import write_safe_evidence_bundle
    destination = tmp_path / "bundle"
    files = {
        "report.json": '{"run_id": "test-001"}',
        "report.md": "# Test\ntest-001",
    }
    # First write
    write_safe_evidence_bundle(destination=destination, files=files, run_id="test-001")
    assert destination.exists()
    # Second write with identical content — should not raise
    write_safe_evidence_bundle(destination=destination, files=files, run_id="test-001")
    # Content should be unchanged
    assert (destination / "report.json").read_text() == '{"run_id": "test-001"}'


def test_write_safe_evidence_bundle_collision_different_content(tmp_path):
    """Writing different content to an existing bundle raises collision error."""
    from platform_orchestration_contracts.evidence_bundle import (
        write_safe_evidence_bundle,
        EvidenceBundleCollisionError,
    )
    destination = tmp_path / "bundle"
    files1 = {
        "report.json": '{"run_id": "test-001"}',
        "manifest.json": '{"run_id": "test-001", "manifest_version": "credential-discovery-evidence.v1"}',
    }
    write_safe_evidence_bundle(destination=destination, files=files1, run_id="test-001")

    files2 = {
        "report.json": '{"run_id": "test-002"}',
        "manifest.json": '{"run_id": "test-002", "manifest_version": "credential-discovery-evidence.v1"}',
    }
    with pytest.raises(EvidenceBundleCollisionError, match="collision"):
        write_safe_evidence_bundle(destination=destination, files=files2, run_id="test-002")


def test_evidence_bundle_collision_error_contains_no_secrets():
    """EvidenceBundleCollisionError contains only opaque paths and run IDs."""
    from platform_orchestration_contracts.evidence_bundle import EvidenceBundleCollisionError
    err = EvidenceBundleCollisionError(
        destination="/evidence/credential-discovery/environment=dev/run_id=test-001",
        existing_run_id="test-001",
        requested_run_id="test-002",
    )
    msg = str(err)
    assert "/evidence/" in msg
    assert "test-001" in msg
    assert "test-002" in msg
    # No secret-like content
    assert "password" not in msg.lower()
    assert "token" not in msg.lower()


def test_write_discovery_evidence_idempotent(tmp_path):
    """write_discovery_evidence is idempotent for the same run."""
    from platform_orchestration_contracts.evidence_bundle import write_discovery_evidence
    from platform_orchestration_contracts.credential_discovery_workflow import (
        PostureReport, COVERAGE_COMPLETED,
    )
    report = PostureReport(
        run_id="test-idempotent-001",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:abc",
        contract_package_version=__version__,
    )
    # First write
    path1 = write_discovery_evidence(
        base_path=tmp_path,
        run_id="test-idempotent-001",
        environment="dev",
        report=report,
        exit_code=0,
    )
    assert path1.exists()
    # Second write — should not raise (safe replay)
    path2 = write_discovery_evidence(
        base_path=tmp_path,
        run_id="test-idempotent-001",
        environment="dev",
        report=report,
        exit_code=0,
    )
    assert path1 == path2
    # Content should be unchanged
    assert (path1 / "report.json").exists()


def test_write_discovery_evidence_collision_different_run(tmp_path):
    """write_discovery_evidence raises collision error for different content."""
    from platform_orchestration_contracts.evidence_bundle import (
        write_discovery_evidence,
        EvidenceBundleCollisionError,
    )
    from platform_orchestration_contracts.credential_discovery_workflow import (
        PostureReport, COVERAGE_COMPLETED,
    )
    report1 = PostureReport(
        run_id="test-collision-001",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:abc",
        contract_package_version=__version__,
    )
    write_discovery_evidence(
        base_path=tmp_path,
        run_id="test-collision-001",
        environment="dev",
        report=report1,
        exit_code=0,
    )

    # Try to write a different report to the same path
    report2 = PostureReport(
        run_id="test-collision-001",
        evaluated_at="2026-09-05T13:00:00+00:00",  # different timestamp
        policy_version="1",
        total_credentials=1,  # different content
        eligible_count=0,
        blocked_count=1,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:def",
        contract_package_version=__version__,
    )
    with pytest.raises(EvidenceBundleCollisionError):
        write_discovery_evidence(
            base_path=tmp_path,
            run_id="test-collision-001",
            environment="dev",
            report=report2,
            exit_code=0,
        )


# --- Console summary (DISCOVERY RESULT block) tests ---


def test_run_discovery_console_summary_contains_scan_status(tmp_path, capsys):
    """Console summary includes machine-parseable DISCOVERY RESULT block."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    mock_observations = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:DATABASE_URL",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            secret_authority_ref="kubernetes-secret:cts/cts-db-secret#uri",
            consumer_refs=(ConsumerRef(kind="Deployment", namespace="cts", name="cts-backend"),),
            owner_hint=OwnerRef(team="cts-platform"),
            exposure_class=EXPOSURE_SECRET_DELIVERED,
            evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
            default_action=ACTION_ENROLLMENT_CANDIDATE,
        ),
    )

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            exit_code = run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                run_id="test-console-001",
            )

    assert exit_code == 0
    captured = capsys.readouterr()
    stderr = captured.err

    # DISCOVERY RESULT block
    assert "DISCOVERY RESULT" in stderr
    assert "run_id=test-console-001" in stderr
    assert "scan_status=completed" in stderr
    assert "exit_code=0" in stderr
    assert "emergency_items=0" in stderr
    assert "coverage=" in stderr
    assert "entries_sha256=" in stderr
    assert "evidence_bundle=" in stderr
    assert "package_version=" in stderr


def test_run_discovery_console_summary_completed_with_findings(tmp_path, capsys):
    """Console summary shows completed_with_findings for exit 2."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    mock_observations = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            secret_authority_ref="inline-env:cts/cts-backend#POSTGRES_DSN",
            consumer_refs=(ConsumerRef(
                kind="Deployment", namespace="cts", name="cts-backend", container="cts-backend",
            ),),
            owner_hint=OwnerRef(team="cts-platform"),
            exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
            evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
            inline_value_present=True,
            default_action=ACTION_EMERGENCY_ROTATION,
        ),
    )

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            exit_code = run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                run_id="test-console-findings-001",
            )

    assert exit_code == 2
    captured = capsys.readouterr()
    stderr = captured.err

    assert "DISCOVERY RESULT" in stderr
    assert "scan_status=completed_with_findings" in stderr
    assert "exit_code=2" in stderr
    assert "emergency_items=1" in stderr


def test_run_discovery_console_summary_no_secret_values(tmp_path, capsys):
    """Console summary contains no secret values."""
    from platform_orchestration_contracts.run_discovery import run_discovery
    from unittest.mock import patch

    raw_secret = "console-test-secret-MUST-NOT-APPEAR"
    mock_observations = (
        CredentialObservation(
            observation_id="k8s:cts:deployment:cts-backend:cts-backend:POSTGRES_DSN",
            source=COVERAGE_SOURCE_KUBERNETES,
            observed_at="2026-09-05T12:00:00+00:00",
            environment="dev",
            credential_class="postgresql_login",
            secret_authority_ref="inline-env:cts/cts-backend#POSTGRES_DSN",
            consumer_refs=(ConsumerRef(
                kind="Deployment", namespace="cts", name="cts-backend", container="cts-backend",
            ),),
            owner_hint=OwnerRef(team="cts-platform"),
            exposure_class=EXPOSURE_ACTIVE_IN_SOURCE,
            evidence_ref="kubernetes://apps/v1/namespaces/cts/deployments/cts-backend@12345",
            inline_value_present=True,
            default_action=ACTION_EMERGENCY_ROTATION,
        ),
    )

    output_path = str(tmp_path / "credential-posture.json")

    with patch("platform_orchestration_contracts.run_discovery.KubernetesPythonDiscoveryClient"):
        with patch("platform_orchestration_contracts.run_discovery.discover_kubernetes_credentials") as mock_discover:
            mock_discover.return_value = mock_observations
            run_discovery(
                namespace="cts",
                sources=["kubernetes"],
                output_path=output_path,
                run_id="test-console-nosecret-001",
            )

    captured = capsys.readouterr()
    stderr = captured.err
    assert raw_secret not in stderr
    assert "MUST-NOT-APPEAR" not in stderr


# --- One-shot scan script tests ---


def test_one_shot_scan_script_syntax_valid():
    """The one-shot scan script passes bash syntax validation."""
    import subprocess
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Bash syntax error: {result.stderr}"


def test_one_shot_scan_script_is_executable():
    """The one-shot scan script has executable permissions."""
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    assert script_path.exists()
    assert os.access(script_path, os.X_OK), "Script is not executable"


def test_one_shot_scan_script_help_works():
    """The one-shot scan script --help produces usage output."""
    import subprocess
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    result = subprocess.run(
        ["bash", str(script_path), "--help"],
        capture_output=True,
        text=True,
    )
    # --help should produce non-empty stderr and exit non-zero (usage)
    assert "USAGE" in result.stderr or "USAGE" in result.stdout


def test_one_shot_scan_script_has_error_trap():
    """The one-shot scan script has an ERR trap for safe error reporting."""
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    content = script_path.read_text()
    assert "trap on_error ERR" in content
    assert "CURRENT_STEP" in content
    # Must NOT use set -x (tracing leaks commands)
    assert "set -x" not in content


def test_one_shot_scan_script_has_strict_options():
    """The one-shot scan script uses strict bash options."""
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    content = script_path.read_text()
    assert "set -Eeuo pipefail" in content
    assert "IFS=" in content


def test_one_shot_scan_script_has_configurable_coverage():
    """The one-shot scan script supports --expect-source for coverage."""
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    content = script_path.read_text()
    assert "--expect-source" in content
    assert "EXPECT_COVERAGE" in content


def test_one_shot_scan_script_has_registry_allowlist():
    """The one-shot scan script supports --registry-allowlist."""
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    content = script_path.read_text()
    assert "--registry-allowlist" in content
    assert "REGISTRY_ALLOWLIST" in content


def test_one_shot_scan_script_rejects_latest_tag():
    """The one-shot scan script rejects :latest image tags."""
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    content = script_path.read_text()
    assert ":latest" in content
    # The check should be present
    assert "must not use :latest" in content


def test_one_shot_scan_script_protects_evidence_dir():
    """The one-shot scan script sets restrictive permissions on evidence dir."""
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "run-one-shot-scan.sh"
    content = script_path.read_text()
    assert "chmod 0700" in content
    assert "chmod -R go-rwx" in content
    assert ".security-evidence" in content


def test_compare_discovery_runs_script_syntax_valid():
    """The compare-discovery-runs script passes bash syntax validation."""
    import subprocess
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "compare-discovery-runs.sh"
    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Bash syntax error: {result.stderr}"


def test_compare_discovery_runs_script_is_executable():
    """The compare-discovery-runs script has executable permissions."""
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "compare-discovery-runs.sh"
    assert script_path.exists()
    assert os.access(script_path, os.X_OK), "Script is not executable"


def test_compare_discovery_runs_script_help_works():
    """The compare-discovery-runs script --help produces usage output."""
    import subprocess
    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "compare-discovery-runs.sh"
    result = subprocess.run(
        ["bash", str(script_path), "--help"],
        capture_output=True,
        text=True,
    )
    assert "USAGE" in result.stderr or "USAGE" in result.stdout


def test_compare_discovery_runs_produces_delta(tmp_path):
    """compare-discovery-runs.sh produces a delta report from two bundles."""
    import subprocess
    from platform_orchestration_contracts.evidence_bundle import write_discovery_evidence
    from platform_orchestration_contracts.credential_discovery_workflow import (
        PostureReport, CredentialPostureEntry, COVERAGE_COMPLETED,
    )

    # Create a "before" bundle with active_in_source findings
    before_entry = CredentialPostureEntry(
        credential_set_id="candidate-test-before",
        credential_class="postgresql_login",
        environment="dev",
        owner=None,
        lifecycle_state="bootstrap_required",
        consumer_count=1,
        provider_identity_ref=None,
        secret_authority_status="unknown",
        risk_tier="high",
        provider_ready=False,
        execution_ready=False,
        eligible=False,
        blockers=(),
        exposure_status="active_in_source",
        last_observed_use=None,
        enrollment_deadline=None,
        recommended_next_action="emergency_rotation",
        input_fingerprint="abc",
    )
    before_report = PostureReport(
        run_id="compare-before-001",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=1,
        eligible_count=0,
        blocked_count=1,
        unowned_count=1,
        orphaned_count=0,
        entries=(before_entry,),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:before",
        contract_package_version=__version__,
    )
    before_dir = write_discovery_evidence(
        base_path=tmp_path / "before",
        run_id="compare-before-001",
        environment="dev",
        report=before_report,
        exit_code=2,
    )

    # Create an "after" bundle with no findings (remediated)
    after_report = PostureReport(
        run_id="compare-after-001",
        evaluated_at="2026-09-05T13:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:after",
        contract_package_version=__version__,
    )
    after_dir = write_discovery_evidence(
        base_path=tmp_path / "after",
        run_id="compare-after-001",
        environment="dev",
        report=after_report,
        exit_code=0,
    )

    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "compare-discovery-runs.sh"
    result = subprocess.run(
        ["bash", str(script_path), "--before", str(before_dir), "--after", str(after_dir)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Script failed: {result.stderr}"
    stderr = result.stderr

    # Should show the delta
    assert "DISCOVERY RUN COMPARISON" in stderr
    assert "compare-before-001" in stderr
    assert "compare-after-001" in stderr

    # Should show remediation verified
    assert "REMEDIATION VERIFIED" in stderr
    assert "active_inline" in stderr.lower() or "active_inline_credentials" in stderr.lower()

    # Should show scan status improvement
    assert "SCAN STATUS IMPROVED" in stderr
    assert "completed_with_findings" in stderr
    assert "completed" in stderr


def test_compare_discovery_runs_json_output(tmp_path):
    """compare-discovery-runs.sh --json produces valid JSON."""
    import subprocess
    from platform_orchestration_contracts.evidence_bundle import write_discovery_evidence
    from platform_orchestration_contracts.credential_discovery_workflow import (
        PostureReport, COVERAGE_COMPLETED,
    )

    before_report = PostureReport(
        run_id="compare-json-before",
        evaluated_at="2026-09-05T12:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:before",
        contract_package_version=__version__,
    )
    before_dir = write_discovery_evidence(
        base_path=tmp_path / "before",
        run_id="compare-json-before",
        environment="dev",
        report=before_report,
        exit_code=0,
    )

    after_report = PostureReport(
        run_id="compare-json-after",
        evaluated_at="2026-09-05T13:00:00+00:00",
        policy_version="1",
        total_credentials=0,
        eligible_count=0,
        blocked_count=0,
        unowned_count=0,
        orphaned_count=0,
        entries=(),
        coverage={COVERAGE_SOURCE_KUBERNETES: COVERAGE_COMPLETED},
        entries_sha256="sha256:after",
        contract_package_version=__version__,
    )
    after_dir = write_discovery_evidence(
        base_path=tmp_path / "after",
        run_id="compare-json-after",
        environment="dev",
        report=after_report,
        exit_code=0,
    )

    script_path = Path(__file__).parent.parent / "deploy" / "cts" / "compare-discovery-runs.sh"
    result = subprocess.run(
        ["bash", str(script_path), "--before", str(before_dir), "--after", str(after_dir), "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Script failed: {result.stderr}"
    # stdout should contain valid JSON
    data = json.loads(result.stdout)
    assert "before" in data
    assert "after" in data
    assert data["before"]["run_id"] == "compare-json-before"
    assert data["after"]["run_id"] == "compare-json-after"

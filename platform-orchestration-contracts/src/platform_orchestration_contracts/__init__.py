"""Platform Orchestration Contracts.

Versioned schemas and adapters for cross-app Temporal workflow integration.
See ADR-036 for the full integration standard.
"""

__version__ = "0.2.0"

from .workflow_envelope import (
    WorkflowEnvelope,
    RequestedBy,
    GovernanceBlock,
    InputRef,
)
from .workflow_result import (
    WorkflowResult,
    Summary,
    ArtifactRef,
    CatalogRef,
    Warning,
    WORKFLOW_STATUS_VALUES,
)
from .workflow_ids import (
    build_workflow_id,
    build_child_workflow_id,
    parse_workflow_id,
    ParsedWorkflowId,
    VALID_DOMAINS,
)
from .artifact_manifest import (
    ArtifactManifest,
    AudioFile,
    ProvenanceBlock,
)
from .error_taxonomy import (
    WorkflowError,
    ERROR_CODES,
    validation_failed,
    resource_unavailable,
    dependency_unavailable,
    retry_exhausted,
    internal_error,
)
from .outbox import (
    WorkflowStartCommand,
    OutboxCommandStatus,
    StartResult,
    START_POLICY_TABLE,
)
from .temporal_client import (
    OrchestrationClient,
    TemporalOrchestrationClient,
    StubOrchestrationClient,
    WorkflowStatus,
    DEFAULT_NAMESPACE,
    TASK_QUEUE_CTS_WORKFLOWS,
    TASK_QUEUE_MEDIA_GPU,
    TASK_QUEUE_CASTING_WORKFLOWS,
    TASK_QUEUE_TTS_GPU,
    TASK_QUEUE_NEXUS_PUBLICATION,
    TASK_QUEUE_MEDIA_IO,
)

__all__ = [
    "__version__",
    # workflow_envelope
    "WorkflowEnvelope",
    "RequestedBy",
    "GovernanceBlock",
    "InputRef",
    # workflow_result
    "WorkflowResult",
    "Summary",
    "ArtifactRef",
    "CatalogRef",
    "Warning",
    "WORKFLOW_STATUS_VALUES",
    # workflow_ids
    "build_workflow_id",
    "build_child_workflow_id",
    "parse_workflow_id",
    "ParsedWorkflowId",
    "VALID_DOMAINS",
    # artifact_manifest
    "ArtifactManifest",
    "AudioFile",
    "ProvenanceBlock",
    # error_taxonomy
    "WorkflowError",
    "ERROR_CODES",
    "validation_failed",
    "resource_unavailable",
    "dependency_unavailable",
    "retry_exhausted",
    "internal_error",
    # outbox
    "WorkflowStartCommand",
    "OutboxCommandStatus",
    "StartResult",
    "START_POLICY_TABLE",
    # temporal_client
    "OrchestrationClient",
    "TemporalOrchestrationClient",
    "StubOrchestrationClient",
    "WorkflowStatus",
    "DEFAULT_NAMESPACE",
    "TASK_QUEUE_CTS_WORKFLOWS",
    "TASK_QUEUE_MEDIA_GPU",
    "TASK_QUEUE_CASTING_WORKFLOWS",
    "TASK_QUEUE_TTS_GPU",
    "TASK_QUEUE_NEXUS_PUBLICATION",
    "TASK_QUEUE_MEDIA_IO",
]

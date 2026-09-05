"""Temporal client adapter.

Standard wrapper that every application uses to interact with Temporal.
Prevents each app from inventing its own client behavior, retry policy,
headers, tracing, or workflow naming scheme. See ADR-036 section 6.1.

This module defines the abstract interface and a default implementation
that wraps the temporalio Python SDK. Applications that cannot import
temporalio (e.g. lightweight CLI tools) may use the stub implementation
and delegate actual submission to a sidecar or HTTP gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from .workflow_envelope import WorkflowEnvelope
from .workflow_result import WorkflowResult


# Standard task queues (ADR-036 section 4)
TASK_QUEUE_CTS_WORKFLOWS = "cts-workflows"
TASK_QUEUE_MEDIA_GPU = "media-gpu"
TASK_QUEUE_CASTING_WORKFLOWS = "casting-workflows"
TASK_QUEUE_TTS_GPU = "tts-gpu"
TASK_QUEUE_NEXUS_PUBLICATION = "nexus-publication"
TASK_QUEUE_MEDIA_IO = "media-io"
# Security task queues (ADR-037) — more privileged than media orchestration;
# must not run in the same worker process as CTS/TTS jobs.
TASK_QUEUE_SECURITY_WORKFLOWS = "security-workflows"
TASK_QUEUE_SECURITY_SECRET_PROVIDER = "security-secret-provider"
TASK_QUEUE_SECURITY_KUBERNETES = "security-kubernetes"
TASK_QUEUE_SECURITY_DATABASE = "security-database"
TASK_QUEUE_SECURITY_OBJECT_STORAGE = "security-object-storage"
# Discovery task queues (ADR-038) — read-only, source-specific isolation.
# Each discovery source has materially different privileges and failure
# modes. A Kubernetes metadata scanner should not acquire database
# catalog permissions; a Git scanner should not obtain object-store
# identity visibility.
TASK_QUEUE_SECURITY_DISCOVERY_KUBERNETES = "security-discovery-kubernetes"
TASK_QUEUE_SECURITY_DISCOVERY_POSTGRES = "security-discovery-postgres"
TASK_QUEUE_SECURITY_DISCOVERY_MINIO = "security-discovery-minio"
TASK_QUEUE_SECURITY_DISCOVERY_GIT = "security-discovery-git-findings"
TASK_QUEUE_SECURITY_CORRELATION = "security-correlation"
TASK_QUEUE_SECURITY_INVENTORY_WRITE = "security-inventory-write"

# Default namespace for the patternfoundry-dev platform
DEFAULT_NAMESPACE = "patternfoundry-dev"


@dataclass(frozen=True)
class WorkflowStatus:
    """Projected workflow status for UI consumption."""

    workflow_id: str
    run_id: Optional[str]
    status: str  # one of WorkflowResult.status values or "running"
    name: str  # workflow type
    task_queue: str
    start_time: Optional[str] = None
    close_time: Optional[str] = None
    correlation_id: Optional[str] = None


class OrchestrationClient(Protocol):
    """Standard interface every application uses to interact with Temporal."""

    async def start(
        self,
        workflow_type: str,
        workflow_id: str,
        task_queue: str,
        envelope: WorkflowEnvelope,
    ) -> str:
        """Start a workflow idempotently. Returns the run_id."""
        ...

    async def signal(
        self,
        workflow_id: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        """Send a signal (e.g. approval, cancellation) to a running workflow."""
        ...

    async def status(self, workflow_id: str) -> WorkflowStatus:
        """Query the current status of a workflow."""
        ...

    async def result(self, workflow_id: str) -> WorkflowResult:
        """Wait for and return the final result of a workflow."""
        ...

    async def cancel(self, workflow_id: str) -> None:
        """Request cancellation of a running workflow."""
        ...


class TemporalOrchestrationClient:
    """Default implementation wrapping the temporalio Python SDK.

    Requires `temporalio` to be installed. Applications without this
    dependency should use StubOrchestrationClient or an HTTP gateway.
    """

    def __init__(
        self,
        temporal_server_url: str,
        namespace: str = DEFAULT_NAMESPACE,
        identity: Optional[str] = None,
    ) -> None:
        self._server_url = temporal_server_url
        self._namespace = namespace
        self._identity = identity or "platform-orchestration"
        self._client: Any = None  # temporalio.client.Client, lazily connected

    async def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from temporalio.client import Client
            except ImportError as exc:
                raise RuntimeError(
                    "temporalio is not installed; "
                    "install it or use StubOrchestrationClient"
                ) from exc
            self._client = await Client.connect(
                self._server_url,
                namespace=self._namespace,
                identity=self._identity,
            )
        return self._client

    async def start(
        self,
        workflow_type: str,
        workflow_id: str,
        task_queue: str,
        envelope: WorkflowEnvelope,
    ) -> str:
        client = await self._ensure_client()
        handle = await client.start_workflow(
            workflow_type,
            envelope.to_dict(),
            id=workflow_id,
            task_queue=task_queue,
        )
        return handle.result_run_id

    async def signal(
        self,
        workflow_id: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        client = await self._ensure_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(name, payload)

    async def status(self, workflow_id: str) -> WorkflowStatus:
        client = await self._ensure_client()
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        return WorkflowStatus(
            workflow_id=workflow_id,
            run_id=desc.result_run_id,
            status=str(desc.status),
            name=desc.workflow_type,
            task_queue=desc.task_queue,
            start_time=desc.start_time.isoformat() if desc.start_time else None,
            close_time=desc.close_time.isoformat() if desc.close_time else None,
        )

    async def result(self, workflow_id: str) -> WorkflowResult:
        client = await self._ensure_client()
        handle = client.get_workflow_handle(workflow_id)
        raw = await handle.result()
        if isinstance(raw, dict):
            return WorkflowResult.from_dict(raw)
        raise TypeError(f"Unexpected workflow result type: {type(raw)}")

    async def cancel(self, workflow_id: str) -> None:
        client = await self._ensure_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.cancel()


class StubOrchestrationClient:
    """In-process stub for testing and for apps without temporalio.

    Does not connect to a real Temporal server. Tracks workflows in memory.
    Useful for unit tests and for CLI tools that delegate actual submission
    to a sidecar.
    """

    def __init__(self) -> None:
        self._workflows: dict[str, dict[str, Any]] = {}

    async def start(
        self,
        workflow_type: str,
        workflow_id: str,
        task_queue: str,
        envelope: WorkflowEnvelope,
    ) -> str:
        if workflow_id in self._workflows:
            # Idempotent: return existing run_id
            return self._workflows[workflow_id]["run_id"]
        run_id = f"stub-run-{workflow_id}"
        self._workflows[workflow_id] = {
            "run_id": run_id,
            "workflow_type": workflow_type,
            "task_queue": task_queue,
            "envelope": envelope,
            "status": "running",
            "signals": [],
        }
        return run_id

    async def signal(
        self,
        workflow_id: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        if workflow_id not in self._workflows:
            raise KeyError(f"Unknown workflow {workflow_id}")
        self._workflows[workflow_id]["signals"].append({"name": name, "payload": payload})

    async def status(self, workflow_id: str) -> WorkflowStatus:
        if workflow_id not in self._workflows:
            raise KeyError(f"Unknown workflow {workflow_id}")
        wf = self._workflows[workflow_id]
        return WorkflowStatus(
            workflow_id=workflow_id,
            run_id=wf["run_id"],
            status=wf["status"],
            name=wf["workflow_type"],
            task_queue=wf["task_queue"],
            correlation_id=wf["envelope"].correlation_id,
        )

    async def result(self, workflow_id: str) -> WorkflowResult:
        raise NotImplementedError(
            "StubOrchestrationClient does not simulate workflow execution"
        )

    async def cancel(self, workflow_id: str) -> None:
        if workflow_id in self._workflows:
            self._workflows[workflow_id]["status"] = "cancelled"

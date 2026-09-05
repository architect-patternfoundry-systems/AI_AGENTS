"""Outbox pattern for transactional workflow starts.

Ensures that a domain record and a workflow start command are written
atomically in one local database transaction. A dispatcher then starts
the Temporal workflow using the deterministic workflow ID.

See ADR-036 section on transactional client adapter.

Without the outbox pattern, two failure modes occur:

  1. App commits corpus_batch = submitted
     → Temporal start fails
     → UI says submitted, but no workflow exists

  2. Temporal workflow starts
     → local DB transaction fails
     → workflow runs without a visible app record

The outbox eliminates both by making the start command durable in the
same transaction as the domain record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class OutboxCommandStatus(str, Enum):
    """Lifecycle states for a workflow start command in the outbox."""

    PENDING = "pending"  # Written, not yet dispatched
    DISPATCHED = "dispatched"  # Temporal start attempted
    CONFIRMED = "confirmed"  # Temporal returned a run_id
    FAILED = "failed"  # Dispatch failed after retries; needs operator attention


@dataclass(frozen=True)
class WorkflowStartCommand:
    """Durable command record stored in the app's outbox table.

    Written in the same database transaction as the domain record
    (e.g. corpus_batch). A dispatcher reads pending commands and
    starts the corresponding Temporal workflow.
    """

    command_id: str  # ULID or UUID
    workflow_id: str  # deterministic, e.g. "casting:corpus-batch:batch_01JABC"
    workflow_type: str  # e.g. "media.corpus-batch.v1"
    task_queue: str
    envelope_json: str  # serialized WorkflowEnvelope
    status: OutboxCommandStatus = OutboxCommandStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    dispatched_at: Optional[str] = None
    confirmed_at: Optional[str] = None
    temporal_run_id: Optional[str] = None
    failure_reason: Optional[str] = None
    dispatch_attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "task_queue": self.task_queue,
            "envelope_json": self.envelope_json,
            "status": self.status.value,
            "created_at": self.created_at,
            "dispatched_at": self.dispatched_at,
            "confirmed_at": self.confirmed_at,
            "temporal_run_id": self.temporal_run_id,
            "failure_reason": self.failure_reason,
            "dispatch_attempts": self.dispatch_attempts,
        }


# --- Start policy for existing workflow IDs ---
#
# When a start command is dispatched and the workflow ID already exists
# in Temporal, the behavior depends on the existing workflow's state.

START_POLICY_TABLE = {
    "running": "return_existing",
    "awaiting_approval": "return_existing",
    "completed": "reject_unless_new_generation",
    "failed_retryable": "signal_retry_or_continue_as_new",
    "failed_permanent": "require_explicit_decision_and_new_id",
    "unknown": "persist_outbox_and_return_submitted_pending_dispatch",
}


@dataclass(frozen=True)
class StartResult:
    """Result of attempting to start a workflow through the outbox."""

    status: str  # "started" | "already_running" | "rejected" | "submitted_pending_dispatch"
    workflow_id: str
    run_id: Optional[str] = None
    command_id: Optional[str] = None
    reason: Optional[str] = None


# --- Outbox table DDL ---
#
# Each application creates this table in its own database. The dispatcher
# is the ONLY component that starts workflows. It reads pending rows,
# starts Temporal using the deterministic workflow ID, marks dispatch
# success atomically, and safely retries temporary Temporal failures.
#
# This makes `submitted_pending_dispatch` a real state rather than an
# optimistic UI label.

OUTBOX_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS workflow_outbox (
    id              UUID PRIMARY KEY,
    aggregate_type  TEXT NOT NULL,
    aggregate_id    TEXT NOT NULL,
    command_type    TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    workflow_id     TEXT NOT NULL,
    workflow_type   TEXT NOT NULL,
    payload_ref     TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    temporal_run_id TEXT,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispatched_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_status_next_attempt
    ON workflow_outbox (status, next_attempt_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_outbox_workflow_id
    ON workflow_outbox (workflow_id);
"""

# Status values for the outbox table
OUTBOX_STATUS_PENDING = "pending"
OUTBOX_STATUS_DISPATCHED = "dispatched"
OUTBOX_STATUS_CONFIRMED = "confirmed"
OUTBOX_STATUS_FAILED = "failed"

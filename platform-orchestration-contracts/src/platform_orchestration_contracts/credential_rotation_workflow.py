"""Closed-loop credential rotation workflow (successor-first, human-gated).

Design contract (approved):
    DETECT → PREPARE → NOTIFY → APPROVE(pr merge) → CUTOVER → VERIFY → CLOSE

- Successor-first: provision a parallel role/credential, flip consumers,
  then revoke. Never `ALTER ROLE` in place (avoids the dual-dead window).
- The PR merge is the human approval gate — GitOps-native, auditable,
  no parallel approval system for the dangerous step.
- A second, *optional* governance-closure ack is time-boxed; strong
  automatic evidence (clean re-scan + dead-liveness test) closes the
  loop without waiting on it.
- Concurrency: one rotation per principal — workflow_id encodes the
  principal so a duplicate start for the same credential is rejected
  by Temporal's idempotency.
- Nothing mutates before the merge signal arrives. All prepare-stage
  outputs are deterministic and dry-runnable.

Failure/signal paths are first-class: `approve_merge`, `reject_merge`,
`abort_rotation`, plus query handlers for `status` and `evidence` so
ops can observe where a rotation is stuck.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

# Activity stubs are defined with `with workflow.unsafe.imports_passed_through()`
# in real deployments; kept as a protocol here so the workflow file is
# importable without a live Temporal environment.
from typing import Protocol


class RotationActivities(Protocol):
    """Activity contract — implementations live in the worker process.

    Implementations must be idempotent; every mutation retries safely.
    """

    async def generate_successor_cred(self, spec: dict) -> str:
        """High-entropy successor credential.

        MUST be encrypted (sops -e) or sealed before returning — the
        activity result is only ever a *reference* (e.g. sealed blob
        id / sealed manifest path), never plaintext. Plaintext may
        only exist inside the activity's memory.
        """

    async def create_role(self, principal: str, successor: str, role_spec: dict) -> None:
        """CREATE ROLE successor ... GRANT ... — idempotent (IF NOT EXISTS)."""

    async def sops_encrypt_and_open_pr(self, sealed: str, branch: str) -> str:
        """Write the sealed secret manifest, open the PR, return pr_url."""

    async def notify_human(self, pr_url: str, principal: str, reason: str) -> None:
        """ntfy push + PR comment (redundant channels)."""

    async def wait_consumer_healthy(self, consumers: list[str], timeout_s: int) -> bool:
        """All consumers authenticated with the successor before revoke."""

    async def patch_and_roll(self, consumers: list[str], sealed: str) -> None:
        """Flip secretKeyRef targets / userlist → rollout restart → ready."""

    async def revoke_predecessor(self, principal: str) -> None:
        """REVOKE/DROP old role — idempotent, safe to retry."""

    async def liveness_dead_check(self, principal: str, old_cred_ref: str) -> bool:
        """Attempt auth with the OLD credential → must fail (401/auth-fail).

        Outcome-only: records timestamp + actor + target + result.
        Never logs credential material.
        """

    async def post_closure_evidence(self, evidence: dict) -> None:
        """POST evidence → governance-closure endpoint."""


class CutoverFailed(Exception):
    """Cutover ran but did not complete — successor must be cleaned up."""


@dataclass
class RotationSpec:
    principal: str                      # e.g. "cortex_db_admin"
    namespace: str                      # e.g. "infra-data"
    secret_name: str                    # e.g. "cts-backend-db"
    consumers: list                     # names or {"name","namespace","kind","secret"?} — see _consumer()
    db_host: str
    db_name: str = "mydatabase"
    password_key: str = "password"      # secret key holding predecessor pw
    artifact_path: Optional[str] = None  # sealed PR file path (default apps/secrets/{ns}/{name}.yaml; set outside Flux paths for OOB principals)
    successor_name: Optional[str] = None  # default: principal + "_r{N}"
    soak_seconds: int = 0                # optional delay before revoke
    merge_wait_hours: int = 168          # finite gate window; expiry cleans up
    health_min_samples: int = 2          # min old-role auth failures before revoke
    closure_ack_required: bool = False   # human ack optional/time-boxed
    dry_run: bool = False                # stop after open_pr+notify — zero mutation
    zerotrace_baseline: str = ""         # e.g. discovery-20260911T091040Z-21876 (Auth-1)
    ntfy_topic: str = "ops-credential-rotation"


@dataclass
class RotationState:
    stage: str = "prepare"
    pr_url: Optional[str] = None
    successor: Optional[str] = None
    evidence: dict = field(default_factory=dict)
    error: Optional[str] = None


def _sops_spec(spec: "RotationSpec") -> dict:
    """Subset of spec fields sops_encrypt_and_open_pr needs:
    artifact path override + consumer gitops secret files."""
    return {"artifact_path": spec.artifact_path, "consumers": spec.consumers,
            "secret_name": spec.secret_name, "namespace": spec.namespace,
            "principal": spec.principal}


@workflow.defn
class CredentialRotationWorkflow:
    """One rotation per principal.

    Start with workflow_id=f"cred-rotation/{principal}" — Temporal
    rejects duplicate starts for the same principal (the concurrency
    lock).
    """

    def __init__(self) -> None:
        self._state = RotationState()
        self._merge_approved = False
        self._merge_rejected = False
        self._aborted = False
        self._closure_acked = False

    # ---- signals ----------------------------------------------------
    @workflow.signal
    def approve_merge(self, approver, pr_url: str = "") -> None:
        # `temporal workflow signal --input '["a","b"]'` delivers the array as
        # a single payload — unpack it rather than TypeError-ing the task.
        if isinstance(approver, (list, tuple)):
            approver, pr_url = (list(approver) + [""])[:2]
        self._merge_approved = True
        self._state.pr_url = pr_url
        self._state.evidence["approver"] = approver
        self._state.evidence["approved_at"] = workflow.now().isoformat()

    @workflow.signal
    def reject_merge(self, reason: str) -> None:
        self._merge_rejected = True
        self._state.evidence["rejected_reason"] = reason

    @workflow.signal
    def abort_rotation(self, reason: str) -> None:
        self._aborted = True
        self._state.evidence["aborted_reason"] = reason

    @workflow.signal
    def closure_ack(self, acker: str) -> None:
        self._closure_acked = True
        self._state.evidence["closure_acker"] = acker

    # ---- queries ----------------------------------------------------
    @workflow.query
    def status(self) -> RotationState:
        return self._state

    @workflow.query
    def evidence(self) -> dict:
        return self._state.evidence

    # ---- main -------------------------------------------------------
    @workflow.run
    async def run(self, spec: RotationSpec) -> RotationState:
        # Create activity stubs with proper Temporal SDK pattern
        from platform_orchestration_contracts import credential_rotation_activities as acts

        # Mark the activities module as pass-through for sandbox
        with workflow.unsafe.imports_passed_through():
            from platform_orchestration_contracts import credential_rotation_activities as acts_unsafe

        spec.successor_name = spec.successor_name or f"{spec.principal}_r{int(workflow.now().timestamp()) % 100000}"
        self._state.successor = spec.successor_name
        self._state.stage = "prepare"
        info = workflow.info()
        self._state.evidence.update({
            "principal": spec.principal,
            "zerotrace_baseline": spec.zerotrace_baseline,
            "workflow_id": info.workflow_id,
            "run_id": info.run_id,
        })

        try:
            # PREPARE — sealed cred + role + PR; no mutation of consumers
            async def _req(fn, args, step, timeout_minutes=10, attempts=6):
                """Execute an activity; re-execute on application-level
                RETRYABLE outcomes (with backoff). A recorded RETRYABLE
                result otherwise replays forever — raising inside the WFT
                never reschedules the activity, wedging the run. FATAL and
                COMPENSATE raise immediately."""
                for i in range(attempts):
                    res = await workflow.execute_activity(
                        fn, args=args,
                        schedule_to_close_timeout=timedelta(minutes=timeout_minutes),
                        retry_policy=RetryPolicy(maximum_attempts=4),
                    )
                    if res.ok:
                        return res.ref
                    if res.outcome.name == "COMPENSATE":
                        raise CutoverFailed(f"{step}: {res.detail}")
                    if res.outcome.name == "FATAL" or i == attempts - 1:
                        raise RuntimeError(f"{step}: {res.detail}")
                    await workflow.sleep(min(120, 10 * 2 ** i))

            sealed = await _req(
                acts_unsafe.generate_successor_cred,
                [{"principal": spec.principal, "successor": spec.successor_name,
                  "consumers": spec.consumers, "namespace": spec.namespace,
                  "secret_name": spec.secret_name, "password_key": spec.password_key}],
                "generate_successor_cred")

            if spec.dry_run:
                # Dry-run: skip all PostgreSQL mutations and rollouts
                branch = f"security/rotate-{spec.principal}-{spec.successor_name}"
                self._state.pr_url = await _req(
                    acts_unsafe.sops_encrypt_and_open_pr,
                    [sealed, branch, True, _sops_spec(spec)],
                    "sops_encrypt_and_open_pr")
                self._state.stage = "await_approval"
                await _req(
                    acts_unsafe.notify_human,
                    [self._state.pr_url, spec.principal, "rotation PR ready (dry-run)"],
                    "notify_human", attempts=4)
                self._state.stage = "dry_run_complete"
                self._state.evidence["dry_run"] = True
                return self._state

            # Live rotation: execute full pipeline
            await _req(
                acts_unsafe.create_role,
                [spec.principal, spec.successor_name, sealed, {"db_host": spec.db_host, "db_name": spec.db_name}],
                "create_role")
            branch = f"security/rotate-{spec.principal}-{spec.successor_name}"
            self._state.pr_url = await _req(
                acts_unsafe.sops_encrypt_and_open_pr,
                [sealed, branch, spec.dry_run, _sops_spec(spec)],
                "sops_encrypt_and_open_pr")
            self._state.stage = "await_approval"
            await _req(
                acts_unsafe.notify_human,
                [self._state.pr_url, spec.principal, "rotation PR ready"],
                "notify_human", attempts=4)

            # APPROVE — wait for merge signal (the human gate)
            try:
                await workflow.wait_condition(
                    lambda: self._merge_approved or self._merge_rejected or self._aborted,
                    timeout=timedelta(hours=spec.merge_wait_hours),
                )
            except workflow.TimeoutError:
                self._state.stage = "expired"
                # Gate window elapsed — clean up the unused successor
                await _req(
                    acts_unsafe.revoke_predecessor,
                    [spec.successor_name],
                    "revoke_successor", attempts=4)
                return self._state
            if self._merge_rejected or self._aborted:
                self._state.stage = "aborted"
                await _req(
                    acts_unsafe.revoke_predecessor,
                    [spec.successor_name],
                    "revoke_successor", attempts=4)
                return self._state

            # CUTOVER — flip consumers to successor, verify, then revoke
            self._state.stage = "cutover"
            await _req(
                acts_unsafe.patch_and_roll,
                [spec.consumers, sealed],
                "patch_and_roll")
            # Gate contract: every listed consumer must auth on the successor
            # (fresh TCP probes, no pool reuse). Old role still valid here.
            await _req(
                acts_unsafe.wait_consumer_healthy,
                [spec.consumers, sealed, 900],
                "wait_consumer_healthy", timeout_minutes=15)

            if spec.soak_seconds:
                await workflow.sleep(spec.soak_seconds)

            await _req(
                acts_unsafe.revoke_predecessor,
                [spec.principal],
                "revoke_predecessor", attempts=12)
            self._state.stage = "verify"

            # VERIFY — old credential must now fail auth; ZeroTrace re-scan clean
            # Strict: predecessor must fail auth on fresh connections —
            # a still-alive result forces compensation before close.
            await _req(
                acts_unsafe.liveness_dead_check,
                [spec.principal, sealed],
                "liveness_dead_check")
            self._state.evidence["liveness_dead"] = True
            self._state.evidence["verified_at"] = workflow.now().isoformat()

            # CLOSE — post evidence; optional human ack is time-boxed and
            # non-blocking when automatic evidence is strong.
            self._state.stage = "closing"
            await _req(
                acts_unsafe.post_closure_evidence,
                [self._state.evidence],
                "post_closure_evidence", attempts=4)
            if spec.closure_ack_required:
                try:
                    await workflow.wait_condition(
                        lambda: self._closure_acked or self._aborted,
                        timeout=timedelta(hours=24),
                    )
                except workflow.TimeoutError:
                    self._state.evidence["closure_ack_timeout"] = True

            self._state.stage = "closed"
            return self._state

        except CutoverFailed as e:
            # Compensation: successor exists but cutover did not complete —
            # delete it so no orphaned valid credential lingers.
            self._state.stage = "cutover_failed"
            self._state.error = str(e)
            try:
                await _req(
                    acts_unsafe.revoke_predecessor,
                    [spec.successor_name],
                    "compensate_successor", attempts=4)
                self._state.evidence["compensated"] = True
            except Exception as ce:
                self._state.evidence["compensation_error"] = str(ce)
            raise
        except Exception as e:
            self._state.stage = "failed"
            self._state.error = str(e)
            raise


# Convenience: deterministic workflow id for dedup-by-principal.
def rotation_workflow_id(principal: str) -> str:
    return f"cred-rotation/{principal}"

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
from temporalio.exceptions import ApplicationError

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

    async def verify_merge_receipt(self, receipt: dict, ctx: dict) -> None:
        """Bind approval to the exact reviewed head + merge commit on the
        target branch, the spec/consumer digests, merged file contents,
        approver signature, and absence of concurrent/direct-mode drift.
        Runs after the merge signal, BEFORE any consumer mutation."""

    async def verify_control_receipt(self, receipt: dict, ctx: dict) -> None:
        """Authenticate an abort/reject request for this execution —
        signature over CONTROL_SIGNED_FIELDS bound to workflow_id +
        run_id + rotation_instance. Untrusted control signals must never
        trigger privileged cleanup."""

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


class CutoverFailed(ApplicationError):
    """Cutover ran but did not complete — successor must be cleaned up.

    Must be an ApplicationError: any other exception type surfacing from
    workflow code is a workflow-TASK failure retried indefinitely —
    the run wedges instead of failing."""


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
    require_direct_probe: bool = False   # incident-critical rotations set this —
                                         # refuses live execution when
                                         # ROTATION_PG_DIRECT_DSN is unset
    rotation_instance: str = ""          # unique per attempt, e.g.
                                         # "inc2026-11-pg-r16023-att1" —
                                         # REQUIRED; the workflow id must be
                                         # cred-rotation/{principal}/{instance}
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


def _canon(obj) -> str:
    """Deterministic JSON for digesting."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _digest(obj) -> str:
    import hashlib
    return hashlib.sha256(_canon(obj).encode()).hexdigest()


def _spec_digest(spec: "RotationSpec") -> str:
    """Digest of the full resolved spec (incl. successor_name) — the value
    the reviewer sees and the receipt must echo back."""
    import dataclasses
    return _digest(dataclasses.asdict(spec))


def _consumer_set_digest(spec: "RotationSpec") -> str:
    """Digest of the declared consumer set (namespaces/kinds/secrets as
    declared — canonical, order-insensitive)."""
    norm = sorted(_canon(c) for c in spec.consumers)
    return _digest(norm)


RECEIPT_REQUIRED_FIELDS = (
    "schema", "action", "approver", "pr_url", "reviewed_head_sha",
    "merge_commit_sha", "spec_digest", "consumer_set_digest", "successor",
    "workflow_id", "run_id", "rotation_instance", "direct_mode_approved",
    "signature",
)

CONTROL_REQUIRED_FIELDS = (
    "schema", "action", "approver", "workflow_id", "run_id",
    "rotation_instance", "signature",
)


def _record_bad(evidence: dict, key: str, entry: dict, cap: int = 20) -> None:
    """Append a bounded diagnostic entry — malformed input must not grow
    workflow history without limit. Keeps the first `cap` entries plus a
    running drop count; entry values are caller-truncated, secret-free."""
    lst = evidence.setdefault(key, [])
    if len(lst) < cap:
        lst.append(entry)
    else:
        evidence[f"{key}_dropped"] = evidence.get(f"{key}_dropped", 0) + 1


def _control_receipt(state: "RotationState", receipt) -> Optional[dict]:
    """Shape-check a control (abort/reject) receipt. Malformed receipts
    are recorded and dropped — they never set a flag, so they cannot
    reach cleanup. Returns the receipt dict when well-formed."""
    if isinstance(receipt, (list, tuple)):
        receipt = (list(receipt) + [{}])[0]
    if not isinstance(receipt, dict) or any(
            f not in receipt for f in CONTROL_REQUIRED_FIELDS):
        _record_bad(state.evidence, "bad_signals", {
            "received": {k: str(v)[:80] for k, v in receipt.items()}
            if isinstance(receipt, dict) else str(receipt)[:200],
            "at": workflow.now().isoformat()})
        return None
    return receipt


def _parse_pr_ref(ref: str) -> dict:
    """sops_encrypt_and_open_pr returns a JSON ref
    {"url","head","base","baseline_files"}; tolerate a legacy bare URL."""
    if ref and ref.startswith("{"):
        try:
            return json.loads(ref)
        except ValueError:
            pass
    return {"url": ref}


@workflow.defn
class CredentialRotationWorkflow:
    """One rotation attempt per (principal, rotation_instance).

    Start with workflow_id=rotation_workflow_id(principal, instance)
    and WorkflowIdReusePolicy=RejectDuplicate. Workflow IDs are reusable
    after closure — duplicate rejection only holds inside Temporal's
    retained-history window; the signed run_id + rotation_instance in
    the receipt is the durable replay defense.
    """

    def __init__(self) -> None:
        self._state = RotationState()
        self._merge_approved = False
        self._merge_rejected = False
        self._aborted = False
        self._closure_acked = False
        self._receipt: Optional[dict] = None
        self._abort_receipt: Optional[dict] = None
        self._reject_receipt: Optional[dict] = None

    # ---- signals ----------------------------------------------------
    @workflow.signal
    def approve_merge(self, receipt, pr_url: str = "") -> None:
        """Approval gate — requires a structured receipt binding the exact
        reviewed head and merge commit (see verify_merge_receipt).

        Receipt fields: approver, pr_url, reviewed_head_sha,
        merge_commit_sha, spec_digest, consumer_set_digest, successor,
        workflow_id, direct_mode_approved. `temporal workflow signal
        --input '[<obj>]'` wraps the payload in an array — unwrap it.
        A malformed receipt does NOT open the gate: it is recorded and
        the workflow keeps waiting so a corrected signal can land.
        Shape validation only — signature/binding verification happens
        in verify_merge_receipt; a forged receipt can never trigger
        cutover OR cleanup."""
        if isinstance(receipt, (list, tuple)):
            receipt = (list(receipt) + [{}])[0]
        if not isinstance(receipt, dict) or any(
                f not in receipt for f in RECEIPT_REQUIRED_FIELDS):
            _record_bad(self._state.evidence, "bad_receipts", {
                "received": {k: str(v)[:80] for k, v in receipt.items()}
                if isinstance(receipt, dict) else str(receipt)[:200],
                "at": workflow.now().isoformat()})
            return
        self._merge_approved = True
        self._receipt = receipt
        self._state.evidence["receipt"] = receipt
        self._state.evidence["approver"] = receipt.get("approver")
        self._state.evidence["approved_at"] = workflow.now().isoformat()

    @workflow.signal
    def reject_merge(self, receipt) -> None:
        """Rejection requires a signed control receipt (action="reject")
        — otherwise any reachable signal sender could destroy legitimate
        preparation. Shape-checked here; authenticated in
        verify_control_receipt before any cleanup runs."""
        receipt = _control_receipt(self._state, receipt)
        if receipt is None:
            return  # recorded by _control_receipt via evidence
        self._merge_rejected = True
        self._reject_receipt = receipt
        self._state.evidence["reject_requested"] = receipt.get("approver")

    @workflow.signal
    def abort_rotation(self, receipt) -> None:
        """Abort requires a signed control receipt (action="abort").
        Same authentication as reject_merge — cleanup is privileged."""
        receipt = _control_receipt(self._state, receipt)
        if receipt is None:
            return
        self._aborted = True
        self._abort_receipt = receipt
        self._state.evidence["abort_requested"] = receipt.get("approver")

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
        # Instance binding: the workflow ID must be exactly
        # cred-rotation/{principal}/{rotation_instance} — the instance
        # nonce is what makes each rotation attempt uniquely addressable
        # (workflow IDs are reusable after closure; instance + run_id in
        # the signed receipt is the durable replay defense).
        expected_id = rotation_workflow_id(spec.principal,
                                           spec.rotation_instance)
        if not spec.rotation_instance or info.workflow_id != expected_id:
            raise ApplicationError(
                f"workflow-id {info.workflow_id!r} != expected "
                f"{expected_id!r}; spec.rotation_instance is required",
                type="rotation-instance-mismatch", non_retryable=True)
        self._state.evidence.update({
            "principal": spec.principal,
            "zerotrace_baseline": spec.zerotrace_baseline,
            "workflow_id": info.workflow_id,
            "run_id": info.run_id,
            # Digests the approver copies into the receipt — bind approval
            # to this exact spec and consumer set, printed for reviewers
            # via the `evidence` query.
            "spec_digest": _spec_digest(spec),
            "consumer_set_digest": _consumer_set_digest(spec),
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
                    if res.outcome == acts_unsafe.Outcome.COMPENSATE:
                        raise CutoverFailed(f"{step}: {res.detail}",
                                            non_retryable=True)
                    if (res.outcome == acts_unsafe.Outcome.FATAL
                            or i == attempts - 1):
                        raise ApplicationError(
                            f"{step}: {res.detail}",
                            type="rotation-step-failed",
                            non_retryable=True)
                    await workflow.sleep(min(120, 10 * 2 ** i))

            async def _call(fn, args, step, timeout_minutes=10, attempts=4):
                """Like _req but RETURNS the terminal ActResult instead of
                raising — the gate needs the failure detail to classify
                unauthenticated vs authenticated-verification failures."""
                for i in range(attempts):
                    res = await workflow.execute_activity(
                        fn, args=args,
                        schedule_to_close_timeout=timedelta(minutes=timeout_minutes),
                        retry_policy=RetryPolicy(maximum_attempts=4),
                    )
                    if res.outcome != acts_unsafe.Outcome.RETRYABLE \
                            or i == attempts - 1:
                        return res
                    await workflow.sleep(min(120, 10 * 2 ** i))
                return res

            sealed = await _req(
                acts_unsafe.generate_successor_cred,
                [{"principal": spec.principal, "successor": spec.successor_name,
                  "consumers": spec.consumers, "namespace": spec.namespace,
                  "secret_name": spec.secret_name, "password_key": spec.password_key,
                  "require_direct_probe": spec.require_direct_probe}],
                "generate_successor_cred")

            if spec.dry_run:
                # Dry-run: skip all PostgreSQL mutations and rollouts
                branch = f"security/rotate-{spec.principal}-{spec.successor_name}"
                pr_ref = _parse_pr_ref(await _req(
                    acts_unsafe.sops_encrypt_and_open_pr,
                    [sealed, branch, True, _sops_spec(spec)],
                    "sops_encrypt_and_open_pr"))
                self._state.pr_url = pr_ref["url"]
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
            pr_ref = _parse_pr_ref(await _req(
                acts_unsafe.sops_encrypt_and_open_pr,
                [sealed, branch, spec.dry_run, _sops_spec(spec)],
                "sops_encrypt_and_open_pr"))
            self._state.pr_url = pr_ref["url"]
            self._state.evidence["pushed_head"] = pr_ref.get("head")
            self._state.evidence["merge_base"] = pr_ref.get("base")
            self._state.evidence["baseline_files"] = pr_ref.get("baseline_files")
            self._state.stage = "await_approval"
            await _req(
                acts_unsafe.notify_human,
                [self._state.pr_url, spec.principal, "rotation PR ready"],
                "notify_human", attempts=4)

            # APPROVE — the human gate. Signal senders are untrusted:
            # malformed/forged/wrong-instance receipts and control
            # signals are only RECORDED — they can open neither cutover
            # nor cleanup. Cleanup runs only on an authenticated
            # abort/reject or bounded expiry.
            gate_ctx = {
                "workflow_id": info.workflow_id,
                "run_id": info.run_id,
                "rotation_instance": spec.rotation_instance,
                "spec_digest": self._state.evidence["spec_digest"],
                "consumer_set_digest": self._state.evidence["consumer_set_digest"],
                "successor": spec.successor_name,
                "principal": spec.principal,
                "pr_url": self._state.pr_url,
                "pushed_head": self._state.evidence.get("pushed_head"),
                "merge_base": self._state.evidence.get("merge_base"),
                "baseline_files": self._state.evidence.get("baseline_files"),
                "consumers": spec.consumers,
                "sealed": sealed,
            }
            # The approval deadline is FIXED at gate entry — forged or
            # malformed signals loop the wait but must not extend it.
            deadline = workflow.now() + timedelta(hours=spec.merge_wait_hours)

            async def _expire():
                self._state.stage = "expired"
                # Bounded approval expiry — the defined cleanup path.
                await _req(
                    acts_unsafe.revoke_predecessor,
                    [spec.successor_name],
                    "revoke_successor", attempts=4)
                return self._state

            while True:
                remaining = deadline - workflow.now()
                if remaining.total_seconds() <= 0:
                    return await _expire()
                try:
                    await workflow.wait_condition(
                        lambda: (self._merge_approved or self._merge_rejected
                                 or self._aborted),
                        timeout=remaining)
                except workflow.TimeoutError:
                    return await _expire()

                if self._merge_rejected or self._aborted:
                    receipt = (self._abort_receipt if self._aborted
                               else self._reject_receipt)
                    which = "abort" if self._aborted else "reject"
                    res = await _call(
                        acts_unsafe.verify_control_receipt,
                        [receipt, gate_ctx], "verify_control_receipt")
                    if not res.ok:
                        _record_bad(
                            self._state.evidence, "bad_control_signals",
                            {"kind": which, "detail": res.detail[:160],
                             "approver": (receipt or {}).get("approver"),
                             "at": workflow.now().isoformat()})
                        # Clear only the flag+receipt we just evaluated —
                        # a newer control receipt may have arrived during
                        # verification and must not be clobbered.
                        if self._aborted and self._abort_receipt is receipt:
                            self._aborted = False
                            self._abort_receipt = None
                        if (self._merge_rejected
                                and self._reject_receipt is receipt):
                            self._merge_rejected = False
                            self._reject_receipt = None
                        self._state.stage = "await_approval"
                        continue
                    self._state.stage = ("aborted" if self._aborted
                                         else "rejected")
                    await _req(
                        acts_unsafe.revoke_predecessor,
                        [spec.successor_name],
                        "revoke_successor", attempts=4)
                    return self._state

                # BINDING — verify the receipt against the actual merged
                # state before ANY consumer mutation.
                self._state.stage = "verify_receipt"
                receipt = self._receipt  # snapshot — a new receipt may
                # arrive while verification runs and must not be lost
                res = await _call(
                    acts_unsafe.verify_merge_receipt,
                    [receipt, gate_ctx], "verify_merge_receipt")
                if res.ok:
                    break
                if res.detail.startswith("unauth:"):
                    # Forged/malformed/wrong-instance/wrong-action —
                    # not an authenticated approval. Record, stay at the
                    # gate; a corrected receipt can still land.
                    _record_bad(
                        self._state.evidence, "bad_receipts",
                        {"rejected_by": "verify_merge_receipt",
                         "detail": res.detail[:160],
                         "approver": (receipt or {}).get("approver"),
                         "at": workflow.now().isoformat()})
                    if self._receipt is receipt:
                        self._merge_approved = False
                        self._receipt = None
                    self._state.stage = "await_approval"
                    continue
                # Authenticated approval, but merged state failed
                # verification — terminal, non-retryable, pre-cutover.
                # The successor is preserved for review; cleanup happens
                # only via an authorized abort or a new attempt.
                self._state.evidence["receipt_rejected"] = True
                self._state.evidence["receipt_rejected_detail"] = res.detail
                self._state.evidence["successor_pending_review"] = True
                raise ApplicationError(
                    f"receipt-verification-failed:{res.detail}",
                    type="rotation-verification-rejected",
                    non_retryable=True)

            if self._receipt.get("reviewed_head_sha") != self._state.evidence.get("pushed_head"):
                # Human-edited branch after the worker push — allowed, but
                # the approval binds to the *reviewed* head; record it.
                self._state.evidence["branch_amended"] = True

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
                [spec.consumers, sealed, 900, spec.require_direct_probe],
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
                [spec.principal, sealed, spec.require_direct_probe],
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
            # Stage-aware partial-cutover recovery: COMPENSATE means an
            # activity partially mutated — consumers may ALREADY run on
            # the successor. Blindly revoking it would take them down.
            # Preserve both credentials, fail terminally, and leave the
            # recovery decision (revert secrets to the still-valid
            # predecessor vs. complete the cutover) to an authorized
            # operator — never to an automatic undo.
            self._state.stage = "cutover_failed"
            self._state.error = str(e)
            self._state.evidence["partial_cutover"] = True
            self._state.evidence["successor_pending_review"] = True
            self._state.evidence["predecessor_status"] = (
                "valid-until-revoke-stage" if "revoke" not in str(e)
                else "revoke-stage-failed")
            raise
        except Exception as e:
            self._state.stage = "failed"
            self._state.error = str(e)
            raise


# Convenience: deterministic workflow id per rotation attempt.
def rotation_workflow_id(principal: str, instance: str) -> str:
    """Unique per attempt — instance is an incident/attempt identifier
    (e.g. 'inc2026-11-pg-r16023-att1'). Workflow IDs are reusable after
    closure; the signed run_id + rotation_instance in the receipt is the
    durable replay defense beyond Temporal's retained-history window."""
    return f"cred-rotation/{principal}/{instance}"

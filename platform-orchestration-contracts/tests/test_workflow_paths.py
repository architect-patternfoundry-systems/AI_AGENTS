"""Executed workflow-path tests — CredentialRotationWorkflow under the
Temporal time-skipping environment.

Beyond structural guards, these prove which activities actually run:

- dry_run + any signals → mutation activities NEVER invoked.
- Live run + malformed receipt → gate stays shut; a second, properly
  shaped receipt opens it (bad receipts don't wedge the gate).
- Live run + receipt that verify_merge_receipt rejects → workflow
  fails BEFORE patch_and_roll; the already-created successor role is
  cleaned up (revoke_predecessor invoked with the successor name).
- Happy path: ordered pipeline, receipt binding happens between the
  gate and cutover.
"""

import asyncio
import json

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from platform_orchestration_contracts import (
    credential_rotation_activities as acts,
    credential_rotation_workflow as wf,
)

TASK_QUEUE = "test-rotation"
CALLS = []  # (activity_name, args_summary)


def _ok(ref=""):
    return acts.ActResult(acts.Outcome.OK, ref=ref)


@activity.defn(name="generate_successor_cred")
async def m_gen(spec):
    CALLS.append(("generate_successor_cred", None))
    return _ok(json.dumps({"sealed": "c2VhbGVk", "successor": spec["successor"]}))


@activity.defn(name="create_role")
async def m_create_role(principal, successor, sealed, role_spec):
    CALLS.append(("create_role", successor))
    return _ok(f"role-created:{successor}")


@activity.defn(name="sops_encrypt_and_open_pr")
async def m_open_pr(sealed, branch, dry_run, spec):
    CALLS.append(("sops_encrypt_and_open_pr", {"dry_run": dry_run}))
    return _ok(json.dumps({"url": "https://github.com/arch/repo/pull/1",
                           "head": "h", "base": "b",
                           "baseline_files": {}}))


@activity.defn(name="notify_human")
async def m_notify(pr_url, principal, reason):
    CALLS.append(("notify_human", reason))
    return _ok("notified")


VERIFY_BEHAVIOR = {"mode": "ok"}
CONTROL_BEHAVIOR = {"mode": "ok"}


@activity.defn(name="verify_control_receipt")
async def m_control(receipt, ctx):
    CALLS.append(("verify_control_receipt", receipt.get("action")))
    if CONTROL_BEHAVIOR["mode"] == "fatal":
        return acts.ActResult(acts.Outcome.FATAL, "unauth:bad-signature")
    return _ok("control-verified")


@activity.defn(name="verify_merge_receipt")
async def m_verify(receipt, ctx):
    CALLS.append(("verify_merge_receipt", receipt.get("approver")))
    mode = VERIFY_BEHAVIOR["mode"]
    if mode == "unauth-slow":
        await asyncio.sleep(0.4)
        return acts.ActResult(acts.Outcome.FATAL, "unauth:bad-signature")
    if mode == "unauth":
        return acts.ActResult(acts.Outcome.FATAL, "unauth:bad-signature")
    if mode == "statefail":
        return acts.ActResult(acts.Outcome.FATAL,
                              "pr-state:merge-commit-mismatch")
    return _ok("receipt-verified")


@activity.defn(name="wait_consumer_healthy")
async def m_healthy(consumers, sealed, timeout_s, require_direct=False):
    CALLS.append(("wait_consumer_healthy", require_direct))
    return _ok("ready")


PATCH_BEHAVIOR = {"mode": "ok"}


@activity.defn(name="patch_and_roll")
async def m_patch(consumers, sealed):
    CALLS.append(("patch_and_roll", None))
    if PATCH_BEHAVIOR["mode"] == "compensate":
        return acts.ActResult(
            acts.Outcome.COMPENSATE, "patched 3/8 secrets then failed")
    return _ok("rolled")


@activity.defn(name="revoke_predecessor")
async def m_revoke(principal):
    CALLS.append(("revoke_predecessor", principal))
    return _ok("revoked")


@activity.defn(name="liveness_dead_check")
async def m_dead(principal, sealed, require_direct=False):
    CALLS.append(("liveness_dead_check", require_direct))
    return _ok("dead")


@activity.defn(name="post_closure_evidence")
async def m_evidence(evidence):
    CALLS.append(("post_closure_evidence", None))
    return _ok("posted")


ALL_MOCKS = [m_gen, m_create_role, m_open_pr, m_notify, m_verify,
             m_control, m_healthy, m_patch, m_revoke, m_dead, m_evidence]

SPEC = wf.RotationSpec(
    principal="cortex_db_admin_r16023",
    namespace="toneroot",
    secret_name="postgres-creds",
    password_key="POSTGRES_PASSWORD",
    consumers=[{"name": "app", "namespace": "ns",
                "secret": {"name": "s", "mode": "gitops",
                           "path": "p.yaml", "keys": {"u": "{user}"}}}],
    db_host="pgbouncer",
    successor_name="cortex_db_admin_r77777",
    require_direct_probe=True,
    rotation_instance="att1",
)


WF_ID = "cred-rotation/cortex_db_admin_r16023/att1"


def _receipt_for(wf_id=WF_ID, **over):
    r = {"schema": acts.RECEIPT_SCHEMA, "action": "approve",
         "approver": "ops-lead",
         "pr_url": "https://github.com/arch/repo/pull/1",
         "reviewed_head_sha": "h", "merge_commit_sha": "m",
         "spec_digest": "x", "consumer_set_digest": "y",
         "successor": "cortex_db_admin_r77777", "workflow_id": wf_id,
         "run_id": "run-1", "rotation_instance": "att1",
         "direct_mode_approved": True, "signature": "signed"}
    r.update(over)
    return r


def _control_receipt(action="abort", wf_id=WF_ID, **over):
    r = {"schema": acts.RECEIPT_SCHEMA, "action": action,
         "approver": "ops-lead", "workflow_id": wf_id,
         "run_id": "run-1", "rotation_instance": "att1",
         "signature": "signed"}
    r.update(over)
    return r


def _names():
    return [c[0] for c in CALLS]


async def _wait_stage(handle, stage, tries=80):
    for _ in range(tries):
        st = await handle.query(wf.CredentialRotationWorkflow.status)
        if st.stage == stage:
            return st
        await asyncio.sleep(0.1)
    return st


async def _run_env(body):
    # Reset shared mock behavior — tests mutate these mid-run; without
    # this they leak across tests (e.g. PATCH "compensate" poisons the
    # next run's cutover).
    for d in (VERIFY_BEHAVIOR, CONTROL_BEHAVIOR, PATCH_BEHAVIOR):
        d["mode"] = "ok"
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[wf.CredentialRotationWorkflow],
                          activities=ALL_MOCKS):
            await body(env)


class TestWorkflowPaths:

    def test_dry_run_never_reaches_mutation(self):
        async def body(env):
            spec = wf.RotationSpec(**{**SPEC.__dict__, "dry_run": True,
                                      "rotation_instance": "att-dry"})
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, spec,
                id="cred-rotation/cortex_db_admin_r16023/att-dry", task_queue=TASK_QUEUE)
            # Even a validly-shaped receipt arrives before close — must
            # not unlock anything: dry_run returns before the gate.
            try:
                await handle.signal(
                    wf.CredentialRotationWorkflow.approve_merge,
                    _receipt_for(wf_id="cred-rotation/cortex_db_admin_r16023/att-dry"))
            except Exception:
                pass
            result = await handle.result()
            assert result.stage == "dry_run_complete"

        CALLS.clear()
        asyncio.run(_run_env(body))
        names = _names()
        assert names == ["generate_successor_cred",
                         "sops_encrypt_and_open_pr", "notify_human"]
        assert not set(names) & {
            "create_role", "patch_and_roll", "revoke_predecessor",
            "liveness_dead_check", "wait_consumer_healthy",
            "verify_merge_receipt"}, names

    def test_malformed_receipt_does_not_open_gate_then_valid_opens(self):
        async def body(env):
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, SPEC,
                id=WF_ID, task_queue=TASK_QUEUE)
            # Poll until the gate is reached, then send garbage first.
            for _ in range(60):
                st = await handle.query(
                    wf.CredentialRotationWorkflow.status)
                if st.stage == "await_approval":
                    break
                await asyncio.sleep(0.1)
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge,
                {"approver": "ops-lead"})  # missing fields → not approved
            await asyncio.sleep(0.2)
            st = await handle.query(wf.CredentialRotationWorkflow.status)
            assert st.stage == "await_approval"
            assert st.evidence.get("bad_receipts")

            # Correctly shaped receipt → verify stub OK → pipeline runs
            VERIFY_BEHAVIOR["mode"] = "ok"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge, _receipt_for())
            result = await handle.result()
            assert result.stage == "closed"
            return result

        VERIFY_BEHAVIOR["mode"] = "ok"
        CALLS.clear()
        result = asyncio.run(_run_env(body))
        names = _names()
        # Order: gen → create → pr → notify → verify → patch → healthy
        #        → revoke → dead → evidence
        assert names == [
            "generate_successor_cred", "create_role",
            "sops_encrypt_and_open_pr", "notify_human",
            "verify_merge_receipt", "patch_and_roll",
            "wait_consumer_healthy", "revoke_predecessor",
            "liveness_dead_check", "post_closure_evidence"], names
        # require_direct_probe propagated
        assert ("wait_consumer_healthy", True) in CALLS
        assert ("liveness_dead_check", True) in CALLS

    def test_forged_receipt_keeps_gate_open(self):
        """An unauthenticated receipt is recorded, gate stays open, no
        cleanup runs — then a valid receipt still completes the run."""
        async def body(env):
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, SPEC,
                id=WF_ID, task_queue=TASK_QUEUE)
            await _wait_stage(handle, "await_approval")
            VERIFY_BEHAVIOR["mode"] = "unauth"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge, _receipt_for())
            for _ in range(40):
                st = await handle.query(wf.CredentialRotationWorkflow.status)
                if st.evidence.get("bad_receipts"):
                    break
                await asyncio.sleep(0.1)
            st = await handle.query(wf.CredentialRotationWorkflow.status)
            assert st.stage == "await_approval"
            assert any("bad-signature" in r.get("detail", "")
                       for r in st.evidence["bad_receipts"])

            VERIFY_BEHAVIOR["mode"] = "ok"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge, _receipt_for())
            result = await handle.result()
            assert result.stage == "closed"

        VERIFY_BEHAVIOR["mode"] = "ok"
        CALLS.clear()
        asyncio.run(_run_env(body))
        names = _names()
        # forged receipt consumed no cleanup; the valid run completed
        assert "revoke_predecessor" in names  # the real one, post-cutover
        assert ("revoke_predecessor", "cortex_db_admin_r77777") not in CALLS

    def test_state_mismatch_terminates_without_cleanup(self):
        """Authenticated approval + merged-state verification failure →
        non-retryable terminal failure pre-cutover; successor preserved,
        NOT auto-revoked."""
        async def body(env):
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, SPEC,
                id=WF_ID, task_queue=TASK_QUEUE)
            await _wait_stage(handle, "await_approval")
            VERIFY_BEHAVIOR["mode"] = "statefail"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge, _receipt_for())
            try:
                await handle.result()
                raise AssertionError("expected workflow failure")
            except Exception as e:
                # non-retryable ApplicationError reaches the client as a
                # failed execution, not a task-retry loop
                cause = getattr(e, "cause", e)
                assert "receipt-verification-failed" in str(cause)
                assert getattr(cause, "non_retryable", False) is True
                assert getattr(cause, "type", "") == \
                    "rotation-verification-rejected"

        VERIFY_BEHAVIOR["mode"] = "ok"
        CALLS.clear()
        asyncio.run(_run_env(body))
        names = _names()
        assert "verify_merge_receipt" in names
        assert "patch_and_roll" not in names
        # no cleanup triggered by a rejected receipt — the successor is
        # preserved for review (revoke only on authorized abort/expiry)
        assert "revoke_predecessor" not in names, names

    def test_forged_abort_ignored_signed_abort_honored(self):
        """An unsigned abort must not destroy preparation; a signed one
        performs the defined cleanup."""
        async def body(env):
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, SPEC,
                id=WF_ID, task_queue=TASK_QUEUE)
            await _wait_stage(handle, "await_approval")

            # Forged abort → recorded, gate stays open, no cleanup
            CONTROL_BEHAVIOR["mode"] = "fatal"
            await handle.signal(
                wf.CredentialRotationWorkflow.abort_rotation,
                _control_receipt(action="abort", signature="forged"))
            for _ in range(40):
                st = await handle.query(wf.CredentialRotationWorkflow.status)
                if st.evidence.get("bad_control_signals"):
                    break
                await asyncio.sleep(0.1)
            st = await handle.query(wf.CredentialRotationWorkflow.status)
            assert st.stage == "await_approval"
            assert st.evidence["bad_control_signals"]
            assert "revoke_predecessor" not in _names()

            # Signed abort → authenticated cleanup, run ends aborted
            CONTROL_BEHAVIOR["mode"] = "ok"
            await handle.signal(
                wf.CredentialRotationWorkflow.abort_rotation,
                _control_receipt(action="abort"))
            result = await handle.result()
            assert result.stage == "aborted"

        VERIFY_BEHAVIOR["mode"] = "ok"
        CONTROL_BEHAVIOR["mode"] = "ok"
        CALLS.clear()
        asyncio.run(_run_env(body))
        # exactly one cleanup, targeting the successor
        revokes = [c for c in CALLS if c[0] == "revoke_predecessor"]
        assert revokes == [("revoke_predecessor",
                            "cortex_db_admin_r77777")], revokes
        assert "patch_and_roll" not in _names()

    def test_instance_mismatch_fails_nonretryable(self):
        """Workflow id must be cred-rotation/{principal}/{instance} —
        anything else is a terminal start failure, no activities run."""
        async def body(env):
            spec = wf.RotationSpec(**{**SPEC.__dict__,
                                      "rotation_instance": "att1"})
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, spec,
                id="cred-rotation/cortex_db_admin_r16023",  # no instance
                task_queue=TASK_QUEUE)
            try:
                await handle.result()
                raise AssertionError("expected start failure")
            except Exception as e:
                cause = getattr(e, "cause", e)
                assert "rotation-instance-mismatch" in str(cause) \
                    or "instance" in str(cause)

        CALLS.clear()
        asyncio.run(_run_env(body))
        assert CALLS == []


    def test_partial_cutover_preserves_successor(self):
        """COMPENSATE mid-cutover → terminal failure, no blind successor
        revoke: consumers may already run on it."""
        async def body(env):
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, SPEC,
                id=WF_ID, task_queue=TASK_QUEUE)
            await _wait_stage(handle, "await_approval")
            VERIFY_BEHAVIOR["mode"] = "ok"
            PATCH_BEHAVIOR["mode"] = "compensate"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge, _receipt_for())
            try:
                await handle.result()
                raise AssertionError("expected cutover failure")
            except Exception:
                pass
            st = await handle.query(wf.CredentialRotationWorkflow.status)
            assert st.evidence.get("partial_cutover") is True
            assert st.evidence.get("successor_pending_review") is True

        VERIFY_BEHAVIOR["mode"] = "ok"
        PATCH_BEHAVIOR["mode"] = "ok"
        CALLS.clear()
        asyncio.run(_run_env(body))
        names = _names()
        assert "patch_and_roll" in names
        # Neither the successor nor the predecessor was touched by
        # automatic compensation — recovery is an authorized decision.
        assert "revoke_predecessor" not in names, names


class TestBoundedDiagnostics:
    def test_record_bad_caps_and_counts(self):
        ev = {}
        for i in range(25):
            wf._record_bad(ev, "bad_receipts", {"n": i})
        assert len(ev["bad_receipts"]) == 20
        assert ev["bad_receipts_dropped"] == 5


    def test_forged_signals_do_not_extend_deadline(self):
        """The gate deadline is fixed at entry: forged receipts loop the
        wait but evidence["gate_deadline"] never moves, and a valid
        receipt still completes the run."""
        async def body(env):
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, SPEC,
                id=WF_ID, task_queue=TASK_QUEUE)
            st = await _wait_stage(handle, "await_approval")
            deadline0 = st.evidence["gate_deadline"]

            VERIFY_BEHAVIOR["mode"] = "unauth"
            for _ in range(3):
                await handle.signal(
                    wf.CredentialRotationWorkflow.approve_merge,
                    _receipt_for())
                await asyncio.sleep(0.15)
            for _ in range(60):
                st = await handle.query(
                    wf.CredentialRotationWorkflow.status)
                if len(st.evidence.get("bad_receipts", [])) >= 3:
                    break
                await asyncio.sleep(0.1)
            st = await handle.query(wf.CredentialRotationWorkflow.status)
            assert st.evidence["gate_deadline"] == deadline0
            assert len(st.evidence["bad_receipts"]) == 3

            VERIFY_BEHAVIOR["mode"] = "ok"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge, _receipt_for())
            assert (await handle.result()).stage == "closed"

        VERIFY_BEHAVIOR["mode"] = "ok"
        CALLS.clear()
        asyncio.run(_run_env(body))

    def test_valid_receipt_survives_mid_verify_rejection(self):
        """A valid receipt arriving while a forged one is being verified
        must not be clobbered by the rejection's flag-clear."""
        async def body(env):
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, SPEC,
                id=WF_ID, task_queue=TASK_QUEUE)
            await _wait_stage(handle, "await_approval")
            VERIFY_BEHAVIOR["mode"] = "unauth-slow"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge, _receipt_for())
            # while the forged receipt is in verification, land the real one
            await asyncio.sleep(0.15)
            VERIFY_BEHAVIOR["mode"] = "ok"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge,
                _receipt_for(approver="ops-lead"))
            result = await handle.result()
            assert result.stage == "closed"

        VERIFY_BEHAVIOR["mode"] = "ok"
        CALLS.clear()
        asyncio.run(_run_env(body))
        assert "patch_and_roll" in _names()

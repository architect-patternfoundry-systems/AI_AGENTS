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


@activity.defn(name="verify_merge_receipt")
async def m_verify(receipt, ctx):
    CALLS.append(("verify_merge_receipt", receipt.get("approver")))
    if VERIFY_BEHAVIOR["mode"] == "fatal":
        return acts.ActResult(acts.Outcome.FATAL, "receipt:bad-signature")
    return _ok("receipt-verified")


@activity.defn(name="wait_consumer_healthy")
async def m_healthy(consumers, sealed, timeout_s, require_direct=False):
    CALLS.append(("wait_consumer_healthy", require_direct))
    return _ok("ready")


@activity.defn(name="patch_and_roll")
async def m_patch(consumers, sealed):
    CALLS.append(("patch_and_roll", None))
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
             m_healthy, m_patch, m_revoke, m_dead, m_evidence]

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
)


def _receipt_for(wf_id="cred-rotation/cortex_db_admin_r16023", **over):
    r = {"approver": "ops-lead",
         "pr_url": "https://github.com/arch/repo/pull/1",
         "reviewed_head_sha": "h", "merge_commit_sha": "m",
         "spec_digest": "x", "consumer_set_digest": "y",
         "successor": "cortex_db_admin_r77777", "workflow_id": wf_id,
         "direct_mode_approved": True, "signature": "signed"}
    r.update(over)
    return r


def _names():
    return [c[0] for c in CALLS]


async def _run_env(body):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[wf.CredentialRotationWorkflow],
                          activities=ALL_MOCKS):
            await body(env)


class TestWorkflowPaths:

    def test_dry_run_never_reaches_mutation(self):
        async def body(env):
            spec = wf.RotationSpec(**{**SPEC.__dict__, "dry_run": True})
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, spec,
                id="cred-rotation/test-dry", task_queue=TASK_QUEUE)
            # Even a validly-shaped receipt arrives before close — must
            # not unlock anything: dry_run returns before the gate.
            try:
                await handle.signal(
                    wf.CredentialRotationWorkflow.approve_merge,
                    _receipt_for(wf_id="cred-rotation/test-dry"))
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
                id="cred-rotation/test-live", task_queue=TASK_QUEUE)
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

    def test_rejected_receipt_stops_before_cutover_and_cleans_up(self):
        async def body(env):
            handle = await env.client.start_workflow(
                wf.CredentialRotationWorkflow.run, SPEC,
                id="cred-rotation/test-reject", task_queue=TASK_QUEUE)
            for _ in range(60):
                st = await handle.query(
                    wf.CredentialRotationWorkflow.status)
                if st.stage == "await_approval":
                    break
                await asyncio.sleep(0.1)
            VERIFY_BEHAVIOR["mode"] = "fatal"
            await handle.signal(
                wf.CredentialRotationWorkflow.approve_merge, _receipt_for())
            try:
                await handle.result()
                raise AssertionError("expected workflow failure")
            except Exception:
                pass

        CALLS.clear()
        asyncio.run(_run_env(body))
        names = _names()
        # verify ran, cutover did not, successor role was cleaned up
        assert "verify_merge_receipt" in names
        assert "patch_and_roll" not in names
        assert "wait_consumer_healthy" not in names
        assert "liveness_dead_check" not in names
        # revoke_predecessor called with the SUCCESSOR (compensation),
        # never with the predecessor
        revokes = [c[1] for c in CALLS if c[0] == "revoke_predecessor"]
        assert revokes == ["cortex_db_admin_r77777"], revokes

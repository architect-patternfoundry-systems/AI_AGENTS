"""Approval-binding tests for the merge-receipt gate (2026-11 incident).

Covers the review requirements for CredentialRotationWorkflow v0.1.24:

- reviewed_head_sha and merge_commit_sha are DISTINCT fields — a PR head
  and its resulting merge commit are not the same commit.
- Receipt binds: repo slug, PR identity, target branch, merged state,
  final head, merge commit on target, workflow id, spec digest,
  successor, consumer-set digest, and explicit direct-mode approval.
- Approver must be on the ROTATION_APPROVERS allowlist — a correctly
  shaped receipt alone is not authorization.
- Secret-freeze guard: intended edits (rotation's own files) pass;
  concurrent target-branch edits or post-merge drift stop the cutover.
- Direct-mode secrets must still hold predecessor-era values.
"""

import asyncio
import base64
import json
from unittest.mock import patch

import pytest

from platform_orchestration_contracts import credential_rotation_activities as acts

MOD = "platform_orchestration_contracts.credential_rotation_activities"

HEAD = "a" * 40
MERGE = "b" * 40
OTHER = "c" * 40
PR_URL = "https://github.com/arch/repo/pull/99"
SLUG = "arch/repo"

CONSUMERS = [
    {"name": "app-a", "namespace": "ns1",
     "secret": {"name": "app-secrets", "mode": "gitops",
                "path": "apps/secrets/ns1/app-secrets.yaml",
                "keys": {"uri": "postgresql://{user}:{pw}@{host}:{port}/{db}"}}},
    {"name": "app-b", "namespace": "ns2",
     "secret": {"name": "pg-creds", "mode": "direct",
                "keys": {"POSTGRES_USER": "{user}", "POSTGRES_PASSWORD": "{pw}"}}},
]

CTX = {
    "workflow_id": "cred-rotation/cortex_db_admin_r16023",
    "run_id": "r1",
    "spec_digest": "specdigest",
    "consumer_set_digest": "consumerdigest",
    "successor": "cortex_db_admin_r77777",
    "principal": "cortex_db_admin_r16023",
    "pr_url": PR_URL,
    "pushed_head": HEAD,
    "merge_base": "base0",
    "baseline_files": {"apps/secrets/ns1/app-secrets.yaml": "blob1"},
    "consumers": CONSUMERS,
    "sealed": "",
}


def _receipt(**over):
    r = {
        "approver": "ops-lead",
        "pr_url": PR_URL,
        "reviewed_head_sha": HEAD,
        "merge_commit_sha": MERGE,
        "spec_digest": "specdigest",
        "consumer_set_digest": "consumerdigest",
        "successor": "cortex_db_admin_r77777",
        "workflow_id": "cred-rotation/cortex_db_admin_r16023",
        "direct_mode_approved": True,
    }
    r.update(over)
    return r


# ---------- pure receipt-field checks ----------

class TestReceiptFields:
    def test_valid_receipt_no_failures(self):
        assert acts._receipt_field_failures(_receipt(), CTX) == []

    def test_missing_each_required_field(self):
        for f in acts.__dict__ and ("approver", "pr_url", "reviewed_head_sha",
                                    "merge_commit_sha", "spec_digest",
                                    "consumer_set_digest", "successor",
                                    "workflow_id", "direct_mode_approved"):
            r = _receipt()
            del r[f]
            assert acts._receipt_field_failures(r, CTX) == [f"missing-field:{f}"]

    @pytest.mark.parametrize("field,bad", [
        ("pr_url", "https://github.com/arch/repo/pull/100"),
        ("workflow_id", "cred-rotation/other"),
        ("spec_digest", "x"),
        ("consumer_set_digest", "x"),
        ("successor", "cortex_db_admin_r99999"),
    ])
    def test_each_binding_mismatch(self, field, bad):
        fails = acts._receipt_field_failures(_receipt(**{field: bad}), CTX)
        assert fails and not any("missing" in f for f in fails)

    def test_direct_mode_requires_explicit_true(self):
        fails = acts._receipt_field_failures(
            _receipt(direct_mode_approved=False), CTX)
        assert "direct-mode-not-explicitly-approved" in fails

    def test_direct_mode_flag_not_required_without_direct_consumers(self):
        ctx = dict(CTX, consumers=[CONSUMERS[0]])  # gitops only
        assert acts._receipt_field_failures(
            _receipt(direct_mode_approved=False), ctx) == []

    def test_head_and_merge_are_distinct_fields(self):
        # A receipt conflating head with merge commit must fail one of the
        # two comparisons — they are checked against different objects.
        r = _receipt(reviewed_head_sha=MERGE, merge_commit_sha=MERGE)
        fails = acts._receipt_field_failures(r, CTX)
        assert fails == []  # field check passes; the PR-state check catches it
        pr = {"state": "MERGED", "baseRefName": "main",
              "headRefOid": HEAD, "mergeCommit": {"oid": MERGE}}
        assert "reviewed-head-mismatch" in acts._pr_state_checks(pr, r, "main")


# ---------- repo/PR parsing and PR-state checks ----------

class TestPrState:
    def test_slug_parsing(self):
        assert acts._pr_url_slug(PR_URL) == SLUG
        assert acts._pr_url_slug("https://github.com/o/r/pull/1") == "o/r"
        assert acts._pr_url_slug("not-a-url") is None

    def test_wrong_repo_slug(self):
        ctx = dict(CTX, pr_url=PR_URL)
        r = _receipt(pr_url="https://github.com/evil/fork/pull/99")
        # field check: pr_url must equal ctx's — catches it first
        assert "pr-url-mismatch" in acts._receipt_field_failures(r, ctx)

    def test_pr_state_all_failures(self):
        pr = {"state": "OPEN", "baseRefName": "develop",
              "headRefOid": OTHER, "mergeCommit": {"oid": OTHER}}
        fails = acts._pr_state_checks(pr, _receipt(), "main")
        assert "pr-not-merged:OPEN" in fails
        assert "wrong-target-branch:develop" in fails
        assert "reviewed-head-mismatch" in fails
        assert "merge-commit-mismatch" in fails


# ---------- concurrent vs intended classification ----------

class TestPathClassification:
    def test_partition(self):
        intended, concurrent = acts._classify_path_changes(
            ["apps/secrets/ns1/app-secrets.yaml", "docs/readme.md"],
            ["apps/secrets/ns1/app-secrets.yaml"])
        assert intended == ["apps/secrets/ns1/app-secrets.yaml"]
        assert concurrent == ["docs/readme.md"]

    def test_affected_paths_from_ctx(self):
        assert acts._affected_secret_paths(CTX) == [
            "apps/secrets/ns1/app-secrets.yaml"]


# ---------- userlist preservation ----------

class TestUserlistPreservation:
    def test_successor_upsert_preserves_others(self):
        raw = '"alice" "p1"\n"bob" "p2"\n'
        rendered, dropped = acts._render_userlist(raw, "succ1", "newpw")
        assert dropped == 0
        assert '"alice" "p1"' in rendered and '"bob" "p2"' in rendered
        assert '"succ1" "newpw"' in rendered

    def test_predecessor_drop_and_successor_add(self):
        raw = '"old_p" "oldpw"\n"other" "keep"\n'
        rendered, _ = acts._render_userlist(raw, "succ1", "npw", drop="old_p")
        assert "old_p" not in rendered
        assert '"other" "keep"' in rendered and '"succ1" "npw"' in rendered

    def test_malformed_lines_counted_not_silent(self):
        raw = '"good" "p"\nGARBAGE LINE\n'
        rendered, dropped = acts._render_userlist(raw, "s", "x")
        assert dropped == 1 and "GARBAGE" not in rendered


# ---------- full activity, mocked I/O ----------

def _gh_payload(state="MERGED", head=HEAD, merge=MERGE, base="main"):
    return {"state": state, "baseRefName": base,
            "headRefOid": head, "mergeCommit": {"oid": merge}}


def _run(receipt, ctx, *, gh=None, git_map=None, kubectl_map=None,
         approvers="ops-lead", sealed_pw="oldpw"):
    """Invoke verify_merge_receipt with all I/O seams mocked.

    git_map: {(args_key): stdout}; keys matched by prefix join.
    kubectl_map: {(ns,name): {key: plaintext}} live .data payloads.
    """
    env = {"ROTATION_REPO_SLUG": SLUG, "ROTATION_REPO_DIR": "/r",
           "ROTATION_TARGET_BRANCH": "main",
           "ROTATION_APPROVERS": approvers,
           "ROTATION_PG_HOST": "pgbouncer", "ROTATION_PG_PORT": "5432",
           "ROTATION_PG_DB": "mydatabase"}

    def fake_gh(*args, env=None):
        return gh if gh is not None else _gh_payload()

    def fake_git(repo, *args, env=None):
        joined = " ".join(args)
        for key, val in (git_map or {}).items():
            if joined.startswith(key):
                return val
        # default: ancestor check / rev-parse / log return sane values
        if "rev-parse" in joined:
            return "blobsha"
        if "log" in joined:
            return ""
        return ""

    class FakeProc:
        returncode = 0

    def fake_run(cmd, **kw):
        joined = " ".join(cmd)
        if "merge-base" in joined and "--is-ancestor" in joined:
            ancestor = (git_map or {}).get("ancestor", True)
            p = FakeProc()
            p.returncode = 0 if ancestor else 1
            return p
        raise AssertionError(f"unexpected subprocess: {joined}")

    def fake_kubectl(*args, **kw):
        # extract -n <ns> and secret name
        ns = args[args.index("-n") + 1]
        name = args[2]
        data = (kubectl_map or {}).get((ns, name))
        if data is None:
            return False, "not-found"
        enc = {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}
        return True, json.dumps(enc)

    with patch.object(acts, "_gh_json", fake_gh), \
         patch.object(acts, "_git_out", fake_git), \
         patch.object(acts.subprocess, "run", fake_run), \
         patch.object(acts, "_kubectl", fake_kubectl), \
         patch.object(acts, "_sealed_field", lambda s, k: sealed_pw), \
         patch.object(acts.os, "environ", {**acts.os.environ, **env}):
        return asyncio.run(acts.verify_merge_receipt(receipt, ctx))


class TestVerifyMergeReceipt:
    def test_happy_path(self):
        # direct consumer ns2/pg-creds still holds predecessor-era values
        live = {("ns2", "pg-creds"): {
            "POSTGRES_USER": "cortex_db_admin_r16023",
            "POSTGRES_PASSWORD": "oldpw"}}
        res = _run(_receipt(), CTX, kubectl_map=live)
        assert res.ok, res.detail

    def test_unauthorized_approver(self):
        res = _run(_receipt(approver="intern"), CTX)
        assert res.outcome is acts.Outcome.FATAL
        assert "unauthorized-approver" in res.detail

    def test_allowlist_unset_fails_closed(self):
        res = _run(_receipt(), CTX, approvers="")
        assert res.outcome is acts.Outcome.FATAL
        assert "approver-allowlist-unset" in res.detail

    def test_wrong_repo(self):
        ctx = dict(CTX, pr_url="https://github.com/evil/x/pull/9")
        res = _run(_receipt(pr_url=ctx["pr_url"]), ctx)
        assert res.outcome is acts.Outcome.FATAL
        assert "wrong-repo" in res.detail

    def test_pr_not_merged(self):
        res = _run(_receipt(), CTX, gh=_gh_payload(state="OPEN"))
        assert res.outcome is acts.Outcome.FATAL
        assert "pr-not-merged" in res.detail

    def test_head_vs_merge_distinction_enforced(self):
        # PR head != reviewed head → fail even though merge commit matches
        res = _run(_receipt(), CTX, gh=_gh_payload(head=OTHER))
        assert res.outcome is acts.Outcome.FATAL
        assert "reviewed-head-mismatch" in res.detail

    def test_merge_commit_mismatch(self):
        res = _run(_receipt(), CTX, gh=_gh_payload(merge=OTHER))
        assert res.outcome is acts.Outcome.FATAL
        assert "merge-commit-mismatch" in res.detail

    def test_merge_commit_not_on_target(self):
        res = _run(_receipt(), CTX, git_map={"ancestor": False})
        assert res.outcome is acts.Outcome.FATAL
        assert "merge-commit-not-on-target" in res.detail

    def test_merged_content_differs(self):
        def git(repo, *args, env=None):
            j = " ".join(args)
            if j.startswith("rev-parse"):
                return "merged-blob" if MERGE in j else "head-blob"
            return ""

        with patch.object(acts, "_gh_json", lambda *a, env=None: _gh_payload()), \
             patch.object(acts, "_git_out", git), \
             patch.object(acts.subprocess, "run",
                          lambda *a, **k: type("P", (), {"returncode": 0})()), \
             patch.object(acts, "_kubectl", lambda *a, **k: (True, "{}")), \
             patch.object(acts, "_sealed_field", lambda s, k: "oldpw"), \
             patch.object(acts.os, "environ",
                          {**acts.os.environ,
                           "ROTATION_REPO_SLUG": SLUG, "ROTATION_REPO_DIR": "/r",
                           "ROTATION_TARGET_BRANCH": "main",
                           "ROTATION_APPROVERS": "ops-lead"}):
            res = asyncio.run(acts.verify_merge_receipt(_receipt(), CTX))
        assert res.outcome is acts.Outcome.FATAL
        assert "merged-content-differs" in res.detail

    def test_concurrent_target_edit_fatal(self):
        res = _run(_receipt(), CTX,
                   git_map={"log --format=%H base0..": "deadbeef123"})
        assert res.outcome is acts.Outcome.FATAL
        assert "concurrent-target-edit" in res.detail

    def test_post_merge_drift_fatal(self):
        def git(repo, *args, env=None):
            j = " ".join(args)
            if j.startswith(f"log --format=%H {MERGE}.."):
                return "newercommit"
            if "rev-parse" in j:
                return "blobsha"
            return ""

        with patch.object(acts, "_gh_json", lambda *a, env=None: _gh_payload()), \
             patch.object(acts, "_git_out", git), \
             patch.object(acts.subprocess, "run",
                          lambda *a, **k: type("P", (), {"returncode": 0})()), \
             patch.object(acts, "_kubectl", lambda *a, **k: (True, "{}")), \
             patch.object(acts, "_sealed_field", lambda s, k: "oldpw"), \
             patch.object(acts.os, "environ",
                          {**acts.os.environ,
                           "ROTATION_REPO_SLUG": SLUG, "ROTATION_REPO_DIR": "/r",
                           "ROTATION_TARGET_BRANCH": "main",
                           "ROTATION_APPROVERS": "ops-lead"}):
            res = asyncio.run(acts.verify_merge_receipt(_receipt(), CTX))
        assert res.outcome is acts.Outcome.FATAL
        assert "post-merge-drift" in res.detail

    def test_direct_secret_drift_fatal(self):
        live = {("ns2", "pg-creds"): {
            "POSTGRES_USER": "someone_else",
            "POSTGRES_PASSWORD": "oldpw"}}
        res = _run(_receipt(), CTX, kubectl_map=live)
        assert res.outcome is acts.Outcome.FATAL
        assert "direct-secret-drift" in res.detail


# ---------- structural guards ----------

class TestDryRunIsolation:
    """The dry-run branch must not reach role creation, cutover, or
    revocation. Verified structurally: in run(), the dry_run block
    returns before any of those activities are invoked."""

    def test_dry_run_returns_before_mutations(self):
        import inspect
        from platform_orchestration_contracts import credential_rotation_workflow as wf
        src = inspect.getsource(wf.CredentialRotationWorkflow.run)
        dry = src.index("if spec.dry_run:")
        create = src.index("acts_unsafe.create_role")
        verify = src.index("acts_unsafe.verify_merge_receipt")
        patch_roll = src.index("acts_unsafe.patch_and_roll")
        revoke = src.index("[spec.principal]")
        block = src[dry:create]
        assert "return self._state" in block
        assert dry < create < verify < patch_roll < revoke

    def test_compensation_revokes_successor_not_predecessor(self):
        import inspect
        from platform_orchestration_contracts import credential_rotation_workflow as wf
        src = inspect.getsource(wf.CredentialRotationWorkflow.run)
        cf = src.index("except CutoverFailed")
        tail = src[cf:]
        # compensation targets the successor — never re-arms the path
        assert "[spec.successor_name]" in tail.split("except Exception")[0]

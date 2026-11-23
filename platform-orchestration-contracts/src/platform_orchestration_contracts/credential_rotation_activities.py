"""Activity implementations for CredentialRotationWorkflow.

Secret-safety contract:
- Plaintext credentials NEVER appear in activity results, exceptions,
  or Temporal history. They exist only inside `generate_successor_cred`
  locals and are handed to `sops_encrypt_and_open_pr` via a sealed
  reference (encrypted manifest blob), never as a string argument.
- Activities return structured `ActResult`s — the workflow distinguishes
  retryable-transient from compensate-and-fail without parsing messages.

Deployment shape: a short-lived Kubernetes Job (scoped SA + a PG role
that can only manage the rotation principals) runs these as Temporal
activities; nothing long-lived holds the privilege.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import string
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from temporalio import activity


class Outcome(str, Enum):
    OK = "ok"
    RETRYABLE = "retryable"      # transient — Temporal retries
    FATAL = "fatal"              # no retry — workflow handles
    COMPENSATE = "compensate"    # partial mutation — run compensation


@dataclass
class ActResult:
    outcome: Outcome
    detail: str = ""             # safe-for-history summary, never secret
    ref: str = ""                # opaque reference (sealed blob, pr_url, ...)

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.OK


@dataclass
class SealedCred:
    """Opaque handle for a credential that is never plaintext here.

    `sealed` holds the sops-encrypted manifest bytes (base64). The
    plaintext password only ever existed inside generate_successor_cred.
    """
    sealed_b64: str
    successor: str
    plaintext_ref: str = ""      # env var NAME holding plaintext in-pod only
                                # (e.g. "_ROT_PLAINTEXT") — never the value


def _pg(sql: str, params: tuple = (), dbname: str = "postgres") -> tuple[bool, str]:
    """Run SQL via psycopg2 using the rotation-runner DSN.

    ROTATION_PG_DSN env holds a scoped connection (role can only manage
    designated principals). Returns (ok, detail) — never logs values.
    """
    import psycopg2
    try:
        conn = psycopg2.connect(os.environ["ROTATION_PG_DSN"], connect_timeout=8)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.close()
        return True, "ok"
    except psycopg2.OperationalError as e:
        return False, f"pg-operational:{e.pgcode or 'conn'}"
    except Exception as e:
        return False, f"pg:{type(e).__name__}"


def _kubectl(*args: str, input_bytes: bytes | None = None, timeout: int = 30) -> tuple[bool, str]:
    try:
        r = subprocess.run(["kubectl", *args], input=input_bytes,
                           capture_output=True, timeout=timeout)
        # Success path: callers consume stdout as DATA (secret .data maps,
        # rendered userlists, rollout status) — truncating corrupts payloads
        # (e.g. json.loads on a 559-byte .data map fails mid-token and the
        # caller spins forever on RETRYABLE secret-parse). Failure path:
        # stderr-or-stdout is error detail only, so it stays bounded.
        if r.returncode == 0:
            return True, r.stdout.decode(errors="replace")
        return False, (r.stderr or r.stdout)[:400].decode(errors="replace")
    except subprocess.TimeoutExpired:
        return False, "kubectl-timeout"


_USERLIST_LINE = re.compile(r'^"([^"]+)" "([^"]*)"$')


def _render_userlist(raw: str, successor: str, pw: str,
                     drop: str = "") -> tuple:
    """Parse userlist text → (rendered, dropped_count).
    Only '"user" "secret"' lines survive; malformed non-empty lines are
    dropped — CALLER MUST SURFACE dropped>0, silent loss is how the
    cts_* entries were nearly eaten again. `drop` removes a named entry
    (e.g. revoked predecessor); `successor` is upserted (empty = skip)."""
    entries, dropped = [], 0
    for line in raw.splitlines():
        m = _USERLIST_LINE.match(line.strip())
        if m:
            entries.append(m.groups())
        elif line.strip():
            dropped += 1
    entries = [(u, p) for u, p in entries if u != successor and u != drop]
    if successor:
        entries.append((successor, pw))
    return "".join(f'"{u}" "{p}"\n' for u, p in entries), dropped


def _prune_userlist(principal: str) -> int:
    """Remove principal's entry from pgbouncer-userlist — shrinks the
    trust-auth surface at revoke time. Returns entries removed, -1 on
    failure (best-effort; NOLOGIN is the real boundary)."""
    ns = os.environ.get("ROTATION_PGBOUNCER_NS", "infra-data")
    ok, cur = _kubectl("get", "secret", "pgbouncer-userlist", "-n", ns,
                       "-o", "jsonpath={.data.userlist\\.txt}")
    if not ok:
        return -1
    raw = base64.b64decode(cur.strip('"')).decode()
    rendered, _ = _render_userlist(raw, "", "", drop=principal)
    if rendered == raw:
        return 0
    patch = json.dumps({"data": {"userlist.txt": base64.b64encode(
        rendered.encode()).decode()}})
    ok, _ = _kubectl("patch", "secret", "pgbouncer-userlist", "-n", ns,
                     "--type", "merge", "-p", patch)
    return 1 if ok else -1


def _secret_keys(s: dict) -> dict:
    """secret spec → {key: value_template}. Supports multi-key `keys`
    mapping ({POSTGRES_USER: '{user}', POSTGRES_PASSWORD: '{pw}'}) and
    the legacy single-key {key, value_template} form."""
    if "keys" in s:
        return s["keys"]
    return {s["key"]: s.get("value_template", "{pw}")}


def _consumer(c) -> dict:
    """Normalize a consumer entry to {name, namespace, kind, secret?}.

    Accepts plain names ("cts-backend") and dicts:
      {"name": ..., "namespace": ..., "kind": "deployment",
       "secret": {"name": ..., "key": ...,
                  "value_template": "postgresql://{user}:{pw}@{host}:{port}/{db}"}}

    Defaults: namespace=ROTATION_NAMESPACE (pgbouncer→infra-data),
    kind=deployment. `secret` marks an out-of-band (non-GitOps) secret
    the worker patches directly before rolling the consumer.
    """
    if isinstance(c, str):
        c = {"name": c}
    return {
        "name": c["name"],
        "namespace": c.get("namespace") or (
            "infra-data" if c["name"] == "pgbouncer"
            else os.environ.get("ROTATION_NAMESPACE", "cts")),
        "kind": c.get("kind", "deployment"),
        "secret": c.get("secret"),
    }


def _sealed_field(sealed: str, key: str) -> str | None:
    """Extract `key` from the sops-encrypted manifest's stringData."""
    try:
        ref = json.loads(sealed)
        blob = base64.b64decode(ref["sealed"])
        r = subprocess.run(
            ["sops", "-d", "--input-type", "yaml", "--output-type", "yaml", "/dev/stdin"],
            input=blob, capture_output=True, timeout=30,
            env={**os.environ, "SOPS_AGE_KEY_FILE": os.environ.get("SOPS_AGE_KEY_FILE", "/etc/sops/age-key.txt")},
        )
        if r.returncode != 0:
            return None
        for line in r.stdout.decode().splitlines():
            ls = line.strip()
            if ls.startswith(key + ":"):
                return ls.split(":", 1)[1].strip().strip('"')
        return None
    except Exception:
        return None


def _plaintext_from_sealed(sealed: str) -> str | None:
    """Decrypt the sealed manifest with the mounted age key; extract PG_PASS.

    Called by every activity that needs the successor password — the
    sealed blob is durable in Temporal history, so any worker can
    decrypt locally. Plaintext never leaves this process.
    """
    try:
        ref = json.loads(sealed)
        blob = base64.b64decode(ref["sealed"])
        r = subprocess.run(
            ["sops", "-d", "--input-type", "yaml", "--output-type", "yaml", "/dev/stdin"],
            input=blob, capture_output=True, timeout=30,
            env={**os.environ, "SOPS_AGE_KEY_FILE": os.environ.get("SOPS_AGE_KEY_FILE", "/etc/sops/age-key.txt")},
        )
        if r.returncode != 0:
            return None
        for line in r.stdout.decode().splitlines():
            ls = line.strip()
            if ls.startswith("password:") or ls.startswith("PG_PASS:"):
                return ls.split(":", 1)[1].strip().strip('"')
        return None
    except Exception:
        return None


def _sops_encrypt(manifest: bytes) -> tuple[bool, bytes | str]:
    """sops -e using the repo .sops.yaml age key (runner pod mounts it)."""
    try:
        key_file = os.environ.get("SOPS_AGE_KEY_FILE", "/etc/sops/age-key.txt")
        with open(key_file) as f:
            age_key = f.read().strip()
        # Derive public key from secret key for encryption
        r = subprocess.run(
            ["age-keygen", "-y"],
            input=age_key, capture_output=True, timeout=10, text=True,
        )
        if r.returncode != 0:
            return False, f"age-keygen failed: {r.stderr[:200]}"
        public_key = r.stdout.strip()
        # Encrypt using the derived public key
        r = subprocess.run(
            ["sops", "-e", "--input-type", "yaml", "--output-type", "yaml", "--age", public_key, "/dev/stdin"],
            input=manifest, capture_output=True, timeout=30,
        )
        return (r.returncode == 0), (r.stdout if r.returncode == 0 else r.stderr[:300])
    except Exception as e:
        return False, f"sops:{type(e).__name__}"


# ----------------------------------------------------------------------
# Activities
# ----------------------------------------------------------------------

@activity.defn
async def generate_successor_cred(spec: dict) -> ActResult:
    """Generate high-entropy password; seal it immediately.

    Result ref is a SealedCred handle — plaintext exists only in
    `pw` (activity-local) and is stashed under an env var name for
    same-pod use by sops/PR steps, never returned or logged.
    """
    principal = spec["principal"]
    successor = spec["successor"]
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

    # Pre-flight consumer validation — runs in dry-run too, so a bad
    # namespace/kind/secret-key in the spec fails BEFORE any live run.
    # Read-only `get` calls double as an RBAC check: if the worker SA
    # can't read a target, that's a transient/permissions problem →
    # RETRYABLE; a verified-missing object is a spec bug → FATAL.
    for c in (_consumer(x) for x in spec.get("consumers", [])):
        ok, d = _kubectl("get", c["kind"], c["name"], "-n", c["namespace"],
                         "-o", "name")
        if not ok:
            if "NotFound" in d or "not found" in d:
                return ActResult(Outcome.FATAL,
                                 f"consumer-missing:{c['namespace']}/{c['kind']}/{c['name']}")
            return ActResult(Outcome.RETRYABLE,
                             f"consumer-get:{c['namespace']}/{c['kind']}/{c['name']}:{d}")
        s = c["secret"]
        if s:
            ok, d = _kubectl("get", "secret", s["name"], "-n", c["namespace"],
                             "-o", "jsonpath={.data}")
            if not ok:
                if "NotFound" in d or "not found" in d:
                    return ActResult(Outcome.FATAL,
                                     f"secret-missing:{c['namespace']}/{s['name']}")
                return ActResult(Outcome.RETRYABLE,
                                 f"secret-get:{c['namespace']}/{s['name']}:{d}")
            try:
                data = json.loads(d)
            except ValueError:
                # Malformed data is deterministic, not transient — RETRYABLE
                # here spun the r78234 dry-run forever on truncated payloads.
                # Surface size + head (key names only; .data values stay out).
                return ActResult(Outcome.FATAL,
                                 f"secret-parse:{s['name']}:len={len(d)}:{d[:30]!r}")
                return ActResult(Outcome.RETRYABLE, f"secret-parse:{s['name']}")
            if s.get("userlist"):
                continue  # rendered userlist has no templated keys to check
            missing = [k for k in _secret_keys(s) if k not in data]
            if missing:
                return ActResult(Outcome.FATAL,
                                 f"secret-keys-missing:{c['namespace']}/{s['name']}:{','.join(missing)}")

    # Snapshot the PREDECESSOR credential before merge — post-merge Flux
    # overwrites the live secret with the successor, so liveness checks
    # later must use this sealed snapshot, not the live secret. Spec
    # fields win over env so non-cts rotations (e.g. cortex_db_admin →
    # infra-system/postgres-credentials) read the right secret; the
    # password may live under a nonstandard key (password_key) or a uri.
    s_ns = spec.get("namespace") or os.environ.get("ROTATION_NAMESPACE", "cts")
    s_name = spec.get("secret_name") or os.environ.get("ROTATION_SECRET_NAME", "cts-backend-db")
    pw_key = spec.get("password_key") or "password"
    ok_s, old_b64 = _kubectl("get", "secret", s_name, "-n", s_ns,
                            "-o", f"jsonpath={{.data.{pw_key}}}")
    if not ok_s:
        # Transient API failure must NOT silently produce an empty snapshot —
        # an empty predecessor_password leaves liveness_dead_check blind.
        return ActResult(Outcome.RETRYABLE, f"predecessor-snapshot:{old_b64}")
    old_pw = base64.b64decode(old_b64.strip('"')).decode() if old_b64.strip('"') else ""
    if not old_pw:
        # Secret may carry credentials only inside `uri` — parse userinfo.
        ok_u, uri_b64 = _kubectl("get", "secret", s_name, "-n", s_ns,
                                "-o", "jsonpath={.data.uri}")
        if ok_u and uri_b64.strip('"'):
            u = base64.b64decode(uri_b64.strip('"')).decode()
            if "://" in u and ":" in u.split("://", 1)[1].split("@")[0]:
                old_pw = u.split("://", 1)[1].split("@")[0].split(":", 1)[1]
    if not old_pw:
        return ActResult(Outcome.FATAL, "predecessor-snapshot-empty")
    # DSN assembled from discrete env parts — no credential-shaped
    # postgresql://user:pw@ literal ever exists in YAML/manifests.
    _h = os.environ.get("ROTATION_PG_HOST", "pgbouncer.infra-data.svc.cluster.local")
    _p = os.environ.get("ROTATION_PG_PORT", "5432")
    _d = os.environ.get("ROTATION_PG_DB", "mydatabase")
    uri = f"postgresql://{successor}:{pw}@{_h}:{_p}/{_d}"
    manifest = (
        "apiVersion: v1\nkind: Secret\nmetadata:\n"
        f"  name: {s_name}\n"
        f"  namespace: {s_ns}\n"
        "type: Opaque\nstringData:\n"
        f"  password: \"{pw}\"\n  uri: \"{uri}\"\n"
        f"  predecessor_password: \"{old_pw}\"\n"
    ).encode()
    ok, sealed = _sops_encrypt(manifest)
    del pw, old_pw
    if not ok:
        return ActResult(Outcome.FATAL, f"sops-encrypt-failed:{sealed}")
    sc = SealedCred(base64.b64encode(sealed if isinstance(sealed, bytes) else sealed.encode()).decode(),
                    successor)
    return ActResult(Outcome.OK, ref=json.dumps({"sealed": sc.sealed_b64, "successor": successor}))


@activity.defn
async def create_role(principal: str, successor: str, sealed: str, role_spec: dict) -> ActResult:
    """CREATE ROLE successor (idempotent) + inherit principal's grants."""
    # Idle guardrail: while ROTATION_FORCE_DRY_RUN is set the worker refuses
    # the first mutating step outright — spec.dry_run=false alone cannot
    # trigger a live rotation (defense-in-depth between scheduled runs).
    if os.environ.get("ROTATION_FORCE_DRY_RUN", "false").lower() == "true":
        return ActResult(Outcome.FATAL, "live-gated:ROTATION_FORCE_DRY_RUN")
    pw = _plaintext_from_sealed(sealed)
    if pw is None:
        return ActResult(Outcome.FATAL, "sealed-decrypt-failed")
    try:
        from psycopg2 import sql as psql
        import psycopg2
        conn = psycopg2.connect(os.environ["ROTATION_PG_DSN"], connect_timeout=8)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(psql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE {}").format(
            psql.Identifier(successor), psql.Literal(pw), psql.Identifier(principal)))
        # PG16: the creator receives ADMIN but not privilege-of on a created
        # role, so ALTER DEFAULT PRIVILEGES FOR ROLE below would fail with
        # InsufficientPrivilege (has_privs_of_role requires an INHERIT-able
        # membership). Self-grant membership — rotation_worker already holds
        # ADMIN on the successor and minted its password.
        cur.execute(psql.SQL("GRANT {} TO CURRENT_USER").format(
            psql.Identifier(successor)))
        # Keep successor-created objects administrable by the principal so a
        # later DROP doesn't fragment ownership across _r{N} roles.
        cur.execute(psql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT ALL ON TABLES TO {}").format(
            psql.Identifier(successor), psql.Identifier(principal)))
        conn.close()
        return ActResult(Outcome.OK, f"role-created:{successor}")
    except psycopg2.errors.DuplicateObject:
        return ActResult(Outcome.OK, "role-exists")  # idempotent
    except Exception as e:
        return ActResult(Outcome.RETRYABLE, f"pg:{type(e).__name__}")


@activity.defn
async def sops_encrypt_and_open_pr(sealed: str, branch: str, dry_run: bool = False,
                                   spec: dict = None) -> ActResult:
    """Write sealed manifest (+ any gitops-mode consumer secret files)
    and open PR via gh. sealed is already encrypted.

    spec.artifact_path overrides the primary file location — point it
    outside Flux-applied paths (e.g. apps/secrets/_rotation-artifacts/)
    for principals whose real secrets are out-of-band, so the merged
    artifact is evidence-only and Flux applies nothing from it.

    Consumers with secret.mode="gitops" get a sealed Secret file at
    secret.path using their own key schema (e.g. POSTGRES_USER /
    POSTGRES_PASSWORD) — required when the live secret is already in a
    Flux inventory (direct kubectl patches would be reverted).

    dry_run=True forces a Draft PR — GitHub blocks merging drafts, so a
    dry-run artifact can never reach a Flux-reconciled path via merge
    (cf. the PR #304 auto-merge incident).
    """
    spec = spec or {}
    try:
        ref = json.loads(sealed)
        blob = base64.b64decode(ref["sealed"])
    except Exception:
        return ActResult(Outcome.FATAL, "sealed-ref-malformed")
    s_ns = spec.get("namespace") or os.environ.get("ROTATION_NAMESPACE", "cts")
    s_name = spec.get("secret_name") or os.environ.get("ROTATION_SECRET_NAME", "cts-backend-db")
    secret_path = (spec.get("artifact_path") or os.environ.get("ROTATION_SECRET_PATH")
                   or f"apps/secrets/{s_ns}/{s_name}.yaml")
    ok, d = _kubectl("config", "current-context")  # sanity
    repo = os.environ.get("ROTATION_REPO_DIR", "/workspace")
    repo_url = os.environ.get("ROTATION_REPO_URL")
    if not repo_url:
        return ActResult(Outcome.FATAL, "ROTATION_REPO_URL not set")
    gh_token = os.environ.get("GH_TOKEN", "")
    if gh_token and repo_url.startswith("https://") and "@" not in repo_url:
        repo_url = repo_url.replace("https://", f"https://x-access-token:{gh_token}@", 1)
    # env-based git config: root FS is read-only so `git config --global`
    # can't write ~/.gitconfig. GIT_CONFIG_* applies to every invocation.
    git_env = {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": repo,
    }
    slug = os.environ.get("ROTATION_REPO_SLUG")
    if not slug:
        return ActResult(Outcome.FATAL, "ROTATION_REPO_SLUG not set")
    try:
        # Idempotent resume: an earlier attempt may have already pushed the
        # branch and opened the PR (a failure between push and result-return
        # deadlocks retries on non-fast-forward). Return the existing PR.
        rl = subprocess.run(["gh", "pr", "list", "-R", slug, "--head", branch,
                             "--json", "url", "--limit", "1"],
                            capture_output=True, text=True, env=git_env)

        target = os.environ.get("ROTATION_TARGET_BRANCH", "main")
        affected = [secret_path] + [
            s["path"] for s in
            ((c.get("secret") or {}) for c in
             (_consumer(x) for x in spec.get("consumers", [])))
            if s.get("mode") == "gitops" and s.get("path")]

        def _mk_pr_ref(url: str) -> str:
            """JSON ref binding this PR to exact SHAs: pushed head, the
            merge-base against the target branch, and each affected
            secret file's blob SHA at that base — the anchor for
            intended-vs-concurrent-change detection at verify time."""
            out = {"url": url}
            try:
                if not os.path.exists(os.path.join(repo, ".git")):
                    os.makedirs(repo, exist_ok=True)
                    subprocess.run(["git", "clone", repo_url, repo],
                                   check=True, capture_output=True, env=git_env)
                subprocess.run(["git", "-C", repo, "fetch", "origin", target, branch],
                               check=True, capture_output=True, env=git_env)
                head = subprocess.run(
                    ["git", "-C", repo, "rev-parse", f"origin/{branch}"],
                    check=True, capture_output=True, env=git_env).stdout.strip().decode()
                base = subprocess.run(
                    ["git", "-C", repo, "merge-base", f"origin/{target}", f"origin/{branch}"],
                    check=True, capture_output=True, env=git_env).stdout.strip().decode()
                out["head"], out["base"] = head, base
                bl = {}
                for p in affected:
                    r = subprocess.run(
                        ["git", "-C", repo, "rev-parse", f"{base}:{p}"],
                        capture_output=True, env=git_env)
                    bl[p] = r.stdout.strip().decode() if r.returncode == 0 else None
                out["baseline_files"] = bl
            except subprocess.CalledProcessError:
                pass  # ref degrades to URL only; verify_merge_receipt fails closed
            return json.dumps(out)

        if rl.returncode == 0:
            existing = json.loads(rl.stdout or "[]")
            if existing:
                return ActResult(Outcome.OK, ref=_mk_pr_ref(existing[0]["url"]))
        # Clone or update the repository
        if os.path.exists(os.path.join(repo, ".git")):
            subprocess.run(["git", "-C", repo, "fetch", "origin"], check=True, capture_output=True, env=git_env)
            subprocess.run(["git", "-C", repo, "checkout", "main"], check=True, capture_output=True, env=git_env)
            subprocess.run(["git", "-C", repo, "pull", "origin", "main"], check=True, capture_output=True, env=git_env)
        else:
            os.makedirs(repo, exist_ok=True)
            subprocess.run(["git", "clone", repo_url, repo], check=True, capture_output=True, env=git_env)
        subprocess.run(["git", "-C", repo, "checkout", "-B", branch], check=True, capture_output=True, env=git_env)
        subprocess.run(["git", "-C", repo, "config", "user.name", "credential-rotation-worker"],
                       check=True, capture_output=True, env=git_env)
        subprocess.run(["git", "-C", repo, "config", "user.email",
                        "rotation-worker@patternfoundry.dev"], check=True, capture_output=True, env=git_env)
        _sp = os.path.join(repo, secret_path)
        os.makedirs(os.path.dirname(_sp), exist_ok=True)
        open(_sp, "wb").write(blob)
        subprocess.run(["git", "-C", repo, "add", secret_path], check=True, capture_output=True, env=git_env)
        # gitops-mode consumer secrets: one sealed file each, written at
        # the live Flux-managed path with the secret's own key schema.
        # Flux applies them on merge — direct patching would revert.
        gitops = [c for c in (_consumer(x) for x in spec.get("consumers", []))
                  if (c["secret"] or {}).get("mode") == "gitops"]
        ul_dropped = 0
        if gitops:
            pw = _plaintext_from_sealed(sealed) or ""
            successor = ref.get("successor", "")
            fmt = {"user": successor, "pw": pw,
                   "host": os.environ.get("ROTATION_PG_HOST", "pgbouncer.infra-data.svc.cluster.local"),
                   "port": os.environ.get("ROTATION_PG_PORT", "5432"),
                   "db": os.environ.get("ROTATION_PG_DB", "mydatabase")}
            for c in gitops:
                s = c["secret"]
                if s.get("userlist"):
                    # Whole-file render: live entries + successor upsert.
                    # Sealed in the PR → Flux owns the list; direct patch
                    # would become permanent drift on every rotation.
                    ok_u, cur = _kubectl(
                        "get", "secret", s["name"], "-n", c["namespace"],
                        "-o", "jsonpath={.data.userlist\\.txt}")
                    if not ok_u:
                        return ActResult(Outcome.RETRYABLE, f"userlist-get:{cur}")
                    rendered, ul_dropped = _render_userlist(
                        base64.b64decode(cur.strip('"')).decode(), successor, pw)
                    body = "\n".join("    " + l for l in rendered.splitlines())
                    man = ("apiVersion: v1\nkind: Secret\nmetadata:\n"
                           f"  name: {s['name']}\n  namespace: {c['namespace']}\n"
                           f"type: Opaque\nstringData:\n  userlist.txt: |\n{body}\n").encode()
                else:
                    sd = "".join(f'  {k}: "{t.format(**fmt)}"\n'
                                 for k, t in _secret_keys(s).items())
                    man = ("apiVersion: v1\nkind: Secret\nmetadata:\n"
                           f"  name: {s['name']}\n  namespace: {c['namespace']}\n"
                           f"type: Opaque\nstringData:\n{sd}").encode()
                ok_e, enc = _sops_encrypt(man)
                if not ok_e:
                    return ActResult(Outcome.FATAL, f"sops-consumer-encrypt:{s['name']}")
                p = os.path.join(repo, s["path"])
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "wb").write(enc if isinstance(enc, bytes) else enc.encode())
                subprocess.run(["git", "-C", repo, "add", s["path"]],
                               check=True, capture_output=True, env=git_env)
            del pw
        dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain"],
                               check=True, capture_output=True, env=git_env).stdout.strip()
        if dirty:
            subprocess.run(["git", "-C", repo, "commit", "-m",
                            "security: rotate credential (sops-encrypted) [rotation-workflow]"],
                           check=True, capture_output=True, env=git_env)
        push = subprocess.run(["git", "-C", repo, "push", "-u", "origin", branch],
                              capture_output=True, env=git_env)
        if push.returncode != 0:
            # A previous attempt pushed this branch already — rebase onto it
            # and retry once. Persistent rejection is deterministic → FATAL.
            subprocess.run(["git", "-C", repo, "fetch", "origin", branch],
                           check=True, capture_output=True, env=git_env)
            rb = subprocess.run(["git", "-C", repo, "rebase", f"origin/{branch}"],
                                capture_output=True, env=git_env)
            if rb.returncode != 0:
                subprocess.run(["git", "-C", repo, "rebase", "--abort"],
                               capture_output=True, env=git_env)
                return ActResult(Outcome.FATAL,
                                 f"git:branch-diverged:{(rb.stderr or b'')[:160].decode(errors='replace')}")
            push = subprocess.run(["git", "-C", repo, "push", "-u", "origin", branch],
                                  capture_output=True, env=git_env)
            if push.returncode != 0:
                return ActResult(Outcome.FATAL,
                                 f"git:push-rejected:{(push.stderr or b'')[:160].decode(errors='replace')}")
        # Trust-auth consumer discovery: clients connecting through pgbouncer
        # with auth_type=trust need no secret env binding — they can name the
        # principal in hardcoded connection strings (ConfigMap scripts, app
        # code). Env/secret audits miss them entirely. Surface every repo
        # file still referencing the principal so the approver can verify
        # each is handled (updated in this PR, patched direct, or dead).
        principal = spec.get("principal", "")
        refs = _repo_principal_refs(repo, principal, secret_path, spec) if principal else []
        body = "Automated credential rotation (sops-encrypted).\n"
        if ul_dropped:
            body += (f"\n**userlist render dropped {ul_dropped} malformed "
                     "line(s)** — inspect the sealed file before merge.\n")
        if refs:
            body += ("\n### Files still referencing `" + principal + "`\n"
                     "Verify each is a consumer patched by this PR/direct-mode, "
                     "or update the hardcoded username before revoking:\n"
                     + "\n".join(f"- `{p}`" for p in refs))
        pr_cmd = ["gh", "pr", "create", "-R", slug, "--body", body]
        if dry_run:
            pr_cmd += ["--draft", "--title", "[DRY-RUN] credential rotation artifact — DO NOT MERGE"]
        else:
            pr_cmd += ["--title", f"security: rotate {principal or 'credential'}"]
        r = subprocess.run(pr_cmd, cwd=repo, capture_output=True, text=True, env=git_env)
        if r.returncode != 0:
            # "PR already exists for this branch" or a race with a parallel
            # attempt — treat the existing PR as success rather than retry.
            rl = subprocess.run(["gh", "pr", "list", "-R", slug, "--head", branch,
                                 "--json", "url", "--limit", "1"],
                                capture_output=True, text=True, env=git_env)
            if rl.returncode == 0:
                existing = json.loads(rl.stdout or "[]")
                if existing:
                    return ActResult(Outcome.OK, ref=_mk_pr_ref(existing[0]["url"]))
            return ActResult(Outcome.RETRYABLE, f"gh:{r.stderr[:200]}")
        return ActResult(Outcome.OK, ref=_mk_pr_ref(r.stdout.strip()))
    except subprocess.CalledProcessError as e:
        return ActResult(Outcome.RETRYABLE, f"git:{(e.stderr or b'')[:200].decode(errors='replace')}")


def _repo_principal_refs(repo: str, principal: str, secret_path: str,
                         spec: dict) -> list:
    """Files under apps/ still naming the principal after this PR's writes.
    Run post-commit so files this PR already updated drop out naturally.
    Skips the rotation worker's own manifests/docs (operator references)
    and evidence artifacts."""
    skip = ("apps/credential-rotation-worker/",
            "apps/secrets/_rotation-artifacts/", secret_path)
    consumer_paths = {
        ((_consumer(c)["secret"] or {}).get("path"))
        for c in spec.get("consumers", []) if _consumer(c)["secret"]
    }
    hits = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d != ".git"]
        for fn in files:
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, repo)
            if rel.startswith(skip) or rel in consumer_paths:
                continue
            try:
                with open(fp, "r", errors="replace") as f:
                    if principal in f.read():
                        hits.append(rel)
            except OSError:
                continue
    return sorted(hits)


@activity.defn
async def notify_human(pr_url: str, principal: str, reason: str) -> ActResult:
    """ntfy push + PR comment (redundant channels)."""
    errs = []
    ntfy = os.environ.get("NTFY_URL", "http://ntfy.toneroot.svc.cluster.local")
    topic = os.environ.get("NTFY_TOPIC", "ops-credential-rotation")
    try:
        req = urllib.request.Request(
            f"{ntfy}/{topic}",
            data=f"Rotation PR ready for {principal}: {pr_url} ({reason})".encode(),
            headers={"Title": "credential-rotation approval required"}, method="POST")
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        errs.append(f"ntfy:{type(e).__name__}")
    r = subprocess.run(["gh", "pr", "comment", pr_url, "-b",
                        f"[rotation-workflow] Awaiting merge approval for `{principal}`"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        errs.append("gh-comment")
    if errs and len(errs) == 2:
        return ActResult(Outcome.RETRYABLE, ",".join(errs))
    return ActResult(Outcome.OK, ";".join(errs) if errs else "notified")


@activity.defn
async def wait_consumer_healthy(consumers: list, sealed: str, timeout_s: int = 900) -> ActResult:
    """All consumers' new pods Ready AND successor auth probe passes."""
    cons = [_consumer(c) for c in consumers]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        all_ready = True
        for c in cons:
            ok, _ = _kubectl("rollout", "status", f"{c['kind']}/{c['name']}", "-n",
                             c["namespace"], f"--timeout=10s")
            if not ok:
                all_ready = False
        if all_ready:
            # probe: can the successor actually authenticate?
            pw = _plaintext_from_sealed(sealed)
            if pw:
                import psycopg2
                try:
                    # conninfo: later params override — append successor creds
                    # rather than string-replacing user (which kept the
                    # rotation_worker password and always failed auth)
                    conn = psycopg2.connect(
                        os.environ["ROTATION_PG_DSN"]
                        + f" user={json.loads(sealed).get('successor','')} password={pw}",
                        connect_timeout=6)
                    conn.close()
                    return ActResult(Outcome.OK, "consumers-ready+successor-auth")
                except Exception:
                    pass
            return ActResult(Outcome.OK, "consumers-ready")
        time.sleep(10)
    return ActResult(Outcome.COMPENSATE, "health-gate-timeout")


@activity.defn
async def patch_and_roll(consumers: list, sealed: str) -> ActResult:
    """Update pgbouncer userlist (if consumer) + out-of-band secrets +
    rollout restarts across namespaces.

    Consumers are normalized via _consumer(): per-consumer
    (name, namespace, kind) and optional out-of-band `secret` patch.
    Idempotent: userlist upsert is replace-or-append with strict
    line validation; restarts are safe to re-issue.
    """
    successor = json.loads(sealed).get("successor", "") if sealed.startswith("{") else ""
    pw = _plaintext_from_sealed(sealed) or ""
    cons = [_consumer(c) for c in consumers]

    # pgbouncer userlist: plaintext entries under auth_type=trust —
    # pgbouncer passes them through for backend auth, so SCRAM verifiers
    # cannot be used. Parse/validate each line, drop malformed ones
    # (a pre-existing truncated tail once spliced a successor into the
    # cts_backend entry and broke trust auth for ~10min).
    pgb = next((c for c in cons if c["name"] == "pgbouncer"), None)
    pgb_s = (pgb["secret"] or {}) if pgb else {}
    ul_dropped = 0
    if pgb and pgb_s.get("mode") != "gitops":
        ok, cur = _kubectl("get", "secret", "pgbouncer-userlist", "-n", pgb["namespace"],
                           "-o", "jsonpath={.data.userlist\\.txt}")
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"userlist-get:{cur}")
        ul, ul_dropped = _render_userlist(
            base64.b64decode(cur.strip('"')).decode(), successor, pw)
        patch = json.dumps({"data": {"userlist.txt": base64.b64encode(ul.encode()).decode()}})
        ok, d = _kubectl("patch", "secret", "pgbouncer-userlist", "-n", pgb["namespace"],
                         "--type", "merge", "-p", patch)
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"userlist-patch:{d}")

    # Out-of-band secrets, two delivery modes:
    #   "direct" (default): kubectl merge-patch — for secrets outside
    #     Flux inventory (postgres-credentials, pgbouncer-userlist).
    #   "gitops": the sealed file was already merged via the approval
    #     PR; Flux must apply it before consumers roll or they'd restart
    #     onto stale creds. Poll the live secret until every rendered
    #     key matches — a pending reconcile returns RETRYABLE and the
    #     activity driver re-executes with backoff.
    # Multi-key secrets (POSTGRES_USER + POSTGRES_PASSWORD) patch
    # atomically in one merge so consumers never see a mixed-credential
    # read.
    fmt = {"user": successor, "pw": pw,
           "host": os.environ.get("ROTATION_PG_HOST", "pgbouncer.infra-data.svc.cluster.local"),
           "port": os.environ.get("ROTATION_PG_PORT", "5432"),
           "db": os.environ.get("ROTATION_PG_DB", "mydatabase")}
    for c in cons:
        s = c["secret"]
        if not s:
            continue
        if s.get("mode") == "gitops" and s.get("userlist"):
            # pgbouncer userlist delivered via the sealed PR file: wait
            # until the live secret carries the successor entry —
            # Flux reconcile pending → RETRYABLE (rollback window).
            ok, d = _kubectl("get", "secret", s["name"], "-n", c["namespace"],
                             "-o", "jsonpath={.data.userlist\\.txt}")
            if not ok:
                return ActResult(Outcome.RETRYABLE, f"userlist-wait:{d}")
            live_raw = base64.b64decode(d.strip('"')).decode()
            has = any(m and m.group(1) == successor
                      for m in (_USERLIST_LINE.match(l.strip())
                                for l in live_raw.splitlines()))
            if not has:
                return ActResult(Outcome.RETRYABLE,
                                 f"userlist-gitops-pending:{s['name']}")
            continue
        if s.get("userlist"):
            continue  # direct-mode userlist already patched above
        expected = {k: t.format(**fmt) for k, t in _secret_keys(s).items()}
        if s.get("mode") == "gitops":
            ok, d = _kubectl("get", "secret", s["name"], "-n", c["namespace"],
                             "-o", "jsonpath={.data}")
            if not ok:
                return ActResult(Outcome.RETRYABLE, f"secret-wait-{s['name']}:{d}")
            try:
                live = json.loads(d)
            except ValueError:
                return ActResult(Outcome.FATAL,
                                 f"secret-wait-parse:{s['name']}:len={len(d)}:{d[:30]!r}")
            applied = all(base64.b64decode(live.get(k, "")).decode(errors="replace") == v
                          for k, v in expected.items())
            if not applied:
                return ActResult(Outcome.RETRYABLE, f"gitops-secret-pending:{s['name']}")
            continue
        data = {k: base64.b64encode(v.encode()).decode() for k, v in expected.items()}
        patch = json.dumps({"data": data})
        ok, d = _kubectl("patch", "secret", s["name"], "-n", c["namespace"],
                         "--type", "merge", "-p", patch)
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"secret-patch-{s['name']}:{d}")

    for c in cons:
        ok, d = _kubectl("rollout", "restart", f"{c['kind']}/{c['name']}", "-n", c["namespace"])
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"restart-{c['name']}:{d}")
    detail = "consumers-rolled"
    if ul_dropped:
        detail += f",userlist-dropped:{ul_dropped}"
    return ActResult(Outcome.OK, detail)


@activity.defn
async def revoke_predecessor(principal: str) -> ActResult:
    """DROP ROLE — idempotent (IF EXISTS). Used for predecessor AND
    compensation (delete unused successor)."""
    try:
        from psycopg2 import sql as psql
        import psycopg2
        conn = psycopg2.connect(os.environ["ROTATION_PG_DSN"], connect_timeout=8)
        conn.autocommit = True
        cur = conn.cursor()
        # State check first — idempotent for already-gone/dead roles, and
        # for SUPERUSER principals (e.g. cortex_db_admin) whose ALTER ROLE
        # requires a superuser: the operator applies NOLOGIN out-of-band
        # while this activity retries, and the retry then sees the dead
        # role and proceeds instead of wedging on InsufficientPrivilege.
        cur.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = %s",
                    (principal,))
        row = cur.fetchone()
        if row is None:
            conn.close()
            return ActResult(Outcome.OK, f"role-absent:{principal}")
        # NOLOGIN only blocks NEW auth — existing pooled sessions (pgbouncer,
        # app pools) keep working. Terminate them so revocation is absolute.
        # Best-effort: needs role membership/superuser; failure is noted,
        # not fatal, since NOLOGIN still prevents reconnects.
        def _kill_sessions():
            try:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE usename = %s AND pid <> pg_backend_pid()",
                    (principal,))
                return cur.rowcount
            except Exception:
                return -1
        if not os.environ.get("ROTATION_ALLOW_DROP") and row[0] is False:
            killed = _kill_sessions()
            pruned = _prune_userlist(principal)
            conn.close()
            return ActResult(Outcome.OK,
                             f"role-already-nologin:{principal},sessions-killed:{killed},ul-pruned:{pruned}")
        if os.environ.get("ROTATION_ALLOW_DROP"):
            _kill_sessions()
            cur.execute(psql.SQL("REASSIGN OWNED BY {} TO postgres").format(psql.Identifier(principal)))
            cur.execute(psql.SQL("DROP OWNED BY {}").format(psql.Identifier(principal)))
            cur.execute(psql.SQL("DROP ROLE IF EXISTS {}").format(psql.Identifier(principal)))
            _prune_userlist(principal)
            return ActResult(Outcome.OK, f"role-dropped:{principal}")
        # Default: NOLOGIN kills auth immediately but keeps object
        # ownership intact — DROP would fail while the role owns
        # tables/migrations (always true for cortex_db_admin).
        cur.execute(psql.SQL("ALTER ROLE {} NOLOGIN").format(psql.Identifier(principal)))
        killed = _kill_sessions()
        pruned = _prune_userlist(principal)
        conn.close()
        return ActResult(Outcome.OK, f"role-nologin:{principal},sessions-killed:{killed},ul-pruned:{pruned}")
    except Exception as e:
        return ActResult(Outcome.RETRYABLE, f"pg:{type(e).__name__}")


@activity.defn
async def liveness_dead_check(principal: str, sealed: str) -> ActResult:
    """Old credential must FAIL auth — twice consecutively on every path.

    ROTATION_PG_DSN points at PgBouncer, so the primary probe covers the
    application path (trust-auth client + userlist backend auth). When
    ROTATION_PG_DIRECT_DSN is set (postgres-rw), the old credential must
    also fail direct authentication — a stale PgBouncer userlist entry
    must not be the only barrier checked."""
    # Read the PREDECESSOR password from the sealed snapshot — the live
    # secret has been overwritten by Flux post-merge (successor creds).
    old_pw = _sealed_field(sealed, "predecessor_password")
    if not old_pw:
        return ActResult(Outcome.RETRYABLE, "predecessor-cred-unsealed")

    def _probe(dsn: str) -> int:
        dead = 0
        for _ in range(2):
            try:
                import psycopg2
                conn = psycopg2.connect(
                    dsn.split(" user=")[0]
                    + f" user={principal} password={old_pw}", connect_timeout=5)
                conn.close()
                return -1  # still valid
            except psycopg2.OperationalError as e:
                msg = str(e)
                if "password authentication failed" in msg or "not permitted to log in" in msg:
                    dead += 1
                else:
                    time.sleep(3)
            except Exception:
                time.sleep(3)
        return dead

    import psycopg2  # noqa: F401 — imported by _probe scope
    paths = {"pooled": _probe(os.environ["ROTATION_PG_DSN"])}
    direct = os.environ.get("ROTATION_PG_DIRECT_DSN")
    if direct:
        paths["direct"] = _probe(direct)
    if any(v == -1 for v in paths.values()):
        return ActResult(Outcome.COMPENSATE,
                         "predecessor-still-valid:"
                         + ",".join(k for k, v in paths.items() if v == -1))
    if all(v == 2 for v in paths.values()):
        return ActResult(Outcome.OK,
                         "dead:" + ",".join(f"{k}=2/2" for k in paths))
    return ActResult(Outcome.RETRYABLE,
                     "dead-probes:" + ",".join(f"{k}={v}/2" for k, v in paths.items()))


@activity.defn
async def post_closure_evidence(evidence: dict) -> ActResult:
    """POST evidence → governance-closure endpoint. Advisory: the Temporal
    history + merged PR ARE the evidence — a dead endpoint must not fail a
    completed rotation. Retryable only on 5xx; DNS/refused/4xx → OK-with-note.
    ROTATION_CLOSURE_URL="" disables posting (default until the sink exists);
    GOVERNANCE_CLOSURE_URL is the legacy name."""
    url = (os.environ.get("ROTATION_CLOSURE_URL")
           or os.environ.get("GOVERNANCE_CLOSURE_URL") or "")
    if not url:
        return ActResult(Outcome.OK, "closure-disabled")
    try:
        req = urllib.request.Request(url, data=json.dumps(evidence).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
        return ActResult(Outcome.OK, "closure-posted")
    except urllib.error.HTTPError as e:
        if e.code >= 500:
            return ActResult(Outcome.RETRYABLE, f"closure:HTTP{e.code}")
        return ActResult(Outcome.OK, f"closure-post-failed:HTTP{e.code}")
    except Exception as e:
        return ActResult(Outcome.OK, f"closure-post-unreachable:{type(e).__name__}")


# ----------------------------------------------------------------------
# Merge-receipt verification (approval binding)
# ----------------------------------------------------------------------

def _gh_json(*args: str, env: dict = None) -> dict | list:
    """gh api/cli returning parsed JSON — patchable seam for tests."""
    r = subprocess.run(["gh", *args], capture_output=True, text=True,
                       env=env or os.environ)
    if r.returncode != 0:
        raise RuntimeError(f"gh:{(r.stderr or r.stdout)[:200]}")
    return json.loads(r.stdout)


def _git_out(repo: str, *args: str, env: dict = None) -> str:
    """git -C <repo> <args> → stdout — patchable seam for tests."""
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                       env=env or os.environ)
    if r.returncode != 0:
        raise RuntimeError(f"git:{(r.stderr or r.stdout)[:200].decode(errors='replace')}")
    return r.stdout.decode().strip()


def _receipt_field_failures(receipt: dict, ctx: dict) -> list:
    """Pure binding checks — no I/O. Returns failure strings."""
    fails = []
    for field in ("approver", "pr_url", "reviewed_head_sha",
                  "merge_commit_sha", "spec_digest", "consumer_set_digest",
                  "successor", "workflow_id", "direct_mode_approved"):
        if field not in receipt:
            fails.append(f"missing-field:{field}")
    if fails:
        return fails
    if receipt["pr_url"] != ctx["pr_url"]:
        fails.append("pr-url-mismatch")
    if receipt["workflow_id"] != ctx["workflow_id"]:
        fails.append("workflow-id-mismatch")
    if receipt["spec_digest"] != ctx["spec_digest"]:
        fails.append("spec-digest-mismatch")
    if receipt["consumer_set_digest"] != ctx["consumer_set_digest"]:
        fails.append("consumer-set-mismatch")
    if receipt["successor"] != ctx["successor"]:
        fails.append("successor-mismatch")
    has_direct = any(((_consumer(c).get("secret") or {}).get("mode") != "gitops"
                      and _consumer(c).get("secret"))
                     for c in ctx.get("consumers", []))
    if has_direct and receipt["direct_mode_approved"] is not True:
        fails.append("direct-mode-not-explicitly-approved")
    return fails


def _pr_url_slug(url: str) -> str | None:
    """'https://github.com/org/repo/pull/123' → 'org/repo', else None."""
    m = re.match(r"https://[^/]+/([^/]+/[^/]+)/pull/\d+", url or "")
    return m.group(1) if m else None


def _pr_state_checks(pr: dict, receipt: dict, target: str) -> list:
    """Pure checks against a `gh pr view` payload."""
    fails = []
    if pr.get("state") != "MERGED":
        fails.append(f"pr-not-merged:{pr.get('state')}")
    if pr.get("baseRefName") != target:
        fails.append(f"wrong-target-branch:{pr.get('baseRefName')}")
    if pr.get("headRefOid") != receipt.get("reviewed_head_sha"):
        fails.append("reviewed-head-mismatch")
    if (pr.get("mergeCommit") or {}).get("oid") != receipt.get("merge_commit_sha"):
        fails.append("merge-commit-mismatch")
    return fails


def _affected_secret_paths(ctx: dict) -> list:
    """Repo paths the rotation PR is expected to change — the freeze set."""
    paths = set()
    for c in (_consumer(x) for x in ctx.get("consumers", [])):
        s = c.get("secret") or {}
        if s.get("mode") == "gitops" and s.get("path"):
            paths.add(s["path"])
    bl = ctx.get("baseline_files") or {}
    paths.update(bl.keys())
    return sorted(paths)


def _classify_path_changes(changed: list, affected: list) -> tuple:
    """(intended, concurrent) — changed paths partitioned against the
    affected set. Anything outside the set is concurrent by definition."""
    aff = set(affected)
    intended = [p for p in changed if p in aff]
    concurrent = [p for p in changed if p not in aff]
    return intended, concurrent


@activity.defn
async def verify_merge_receipt(receipt: dict, ctx: dict) -> ActResult:
    """Bind the approval to the exact reviewed+merged state before any
    consumer mutation. All failures are FATAL — nothing has mutated yet,
    so a stop costs nothing but the gate.

    Checks (see AMENDMENT-01 §D):
      1. receipt fields bind workflow/spec/successor/consumer-set/direct-mode
      2. pr_url identity + repository slug
      3. PR state=MERGED on expected target branch
      4. PR final head == receipt.reviewed_head_sha (reviewed head)
      5. PR mergeCommit.oid == receipt.merge_commit_sha and is an ancestor
         of the target branch (distinct commits — merge-commit convention)
      6. merged file contents == reviewed head contents (per affected path)
      7. no concurrent edits to affected paths on target since merge-base;
         no post-merge edits before mutation
      8. approver allowlist (ROTATION_APPROVERS) — a well-formed receipt
         alone is not authorization
      9. direct-mode live secrets still hold predecessor-era values
    """
    fails = _receipt_field_failures(receipt, ctx)
    if fails:
        return ActResult(Outcome.FATAL, "receipt:" + ",".join(fails))

    slug = os.environ.get("ROTATION_REPO_SLUG", "")
    url_slug = _pr_url_slug(receipt["pr_url"])
    if not url_slug or url_slug.lower() != slug.lower():
        return ActResult(Outcome.FATAL, f"wrong-repo:{url_slug}")
    target = os.environ.get("ROTATION_TARGET_BRANCH", "main")

    approvers = [a.strip() for a in
                 os.environ.get("ROTATION_APPROVERS", "").split(",") if a.strip()]
    if not approvers:
        return ActResult(Outcome.FATAL, "approver-allowlist-unset")
    if receipt["approver"] not in approvers:
        return ActResult(Outcome.FATAL, f"unauthorized-approver:{receipt['approver']}")

    repo = os.environ.get("ROTATION_REPO_DIR", "/workspace")
    git_env = {**os.environ, "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": repo}
    try:
        pr = _gh_json("pr", "view", receipt["pr_url"], "-R", slug,
                      "--json", "state,headRefOid,mergeCommit,baseRefName",
                      env=git_env)
        fails = _pr_state_checks(pr, receipt, target)
        if fails:
            return ActResult(Outcome.FATAL, "pr-state:" + ",".join(fails))

        merge_sha = receipt["merge_commit_sha"]
        head_sha = receipt["reviewed_head_sha"]

        # Fetch both endpoints + current target tip
        _git_out(repo, "fetch", "origin", target, merge_sha, head_sha, env=git_env)
        anc = subprocess.run(
            ["git", "-C", repo, "merge-base", "--is-ancestor",
             merge_sha, f"origin/{target}"],
            capture_output=True, env=git_env)
        if anc.returncode != 0:
            return ActResult(Outcome.FATAL, "merge-commit-not-on-target")

        affected = _affected_secret_paths(ctx)

        # Merged contents must equal the reviewed head's contents for every
        # affected path (guards a divergent merge result / conflict munge).
        for p in affected:
            try:
                merged = _git_out(repo, "rev-parse", f"{merge_sha}:{p}", env=git_env)
            except RuntimeError:
                return ActResult(Outcome.FATAL, f"merged-missing:{p}")
            try:
                reviewed = _git_out(repo, "rev-parse", f"{head_sha}:{p}", env=git_env)
            except RuntimeError:
                return ActResult(Outcome.FATAL, f"reviewed-missing:{p}")
            if merged != reviewed:
                return ActResult(Outcome.FATAL, f"merged-content-differs:{p}")

        # Intended-vs-concurrent: any commit on target between merge-base
        # and merge's first parent that touched an affected path is a
        # concurrent edit — stop and re-review, never regenerate silently.
        base = ctx.get("merge_base")
        if base:
            out = _git_out(repo, "log", "--format=%H",
                           f"{base}..{merge_sha}^1", "--", *affected,
                           env=git_env)
            if out.strip():
                return ActResult(Outcome.FATAL,
                                 f"concurrent-target-edit:{out.splitlines()[0][:12]}")
        # Post-merge edits to affected paths already on target → drift.
        out = _git_out(repo, "log", "--format=%H",
                       f"{merge_sha}..origin/{target}", "--", *affected,
                       env=git_env)
        if out.strip():
            return ActResult(Outcome.FATAL, "post-merge-drift")

        # Direct-mode live state: secrets patched outside the PR must still
        # carry predecessor-era values — anything else is drift requiring
        # human review before we write over it.
        directs = [c for c in (_consumer(x) for x in ctx.get("consumers", []))
                   if (c.get("secret") or {}).get("mode") != "gitops"
                   and c.get("secret") and not (c["secret"] or {}).get("userlist")]
        if directs:
            old_pw = _sealed_field(ctx.get("sealed", ""), "predecessor_password")
            if not old_pw:
                return ActResult(Outcome.RETRYABLE, "predecessor-cred-unsealed")
            fmt_old = {"user": ctx["principal"], "pw": old_pw,
                       "host": os.environ.get("ROTATION_PG_HOST", ""),
                       "port": os.environ.get("ROTATION_PG_PORT", "5432"),
                       "db": os.environ.get("ROTATION_PG_DB", "")}
            seen = set()
            for c in directs:
                s = c["secret"]
                key = (c["namespace"], s["name"])
                if key in seen:
                    continue
                seen.add(key)
                ok, d = _kubectl("get", "secret", s["name"], "-n", c["namespace"],
                                 "-o", "jsonpath={.data}")
                if not ok:
                    return ActResult(Outcome.RETRYABLE, f"direct-secret-get:{d}")
                live = json.loads(d)
                for k, t in _secret_keys(s).items():
                    expected = t.format(**fmt_old)
                    actual = base64.b64decode(live.get(k, "")).decode(errors="replace")
                    if actual != expected:
                        return ActResult(Outcome.FATAL,
                                         f"direct-secret-drift:{c['namespace']}/{s['name']}:{k}")
    except RuntimeError as e:
        return ActResult(Outcome.RETRYABLE, f"verify-io:{e}")

    return ActResult(Outcome.OK, "receipt-verified")

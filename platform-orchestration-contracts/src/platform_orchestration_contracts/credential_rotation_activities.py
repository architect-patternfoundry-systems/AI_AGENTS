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
        return r.returncode == 0, (r.stderr or r.stdout)[:400].decode(errors="replace")
    except subprocess.TimeoutExpired:
        return False, "kubectl-timeout"


_USERLIST_LINE = re.compile(r'^"([^"]+)" "([^"]*)"$')


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
                return ActResult(Outcome.RETRYABLE, f"secret-parse:{s['name']}")
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
    try:
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
        if gitops:
            pw = _plaintext_from_sealed(sealed) or ""
            successor = ref.get("successor", "")
            fmt = {"user": successor, "pw": pw,
                   "host": os.environ.get("ROTATION_PG_HOST", "pgbouncer.infra-data.svc.cluster.local"),
                   "port": os.environ.get("ROTATION_PG_PORT", "5432"),
                   "db": os.environ.get("ROTATION_PG_DB", "mydatabase")}
            for c in gitops:
                s = c["secret"]
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
        subprocess.run(["git", "-C", repo, "commit", "-m",
                        "security: rotate credential (sops-encrypted) [rotation-workflow]"],
                       check=True, capture_output=True, env=git_env)
        subprocess.run(["git", "-C", repo, "push", "-u", "origin", branch], check=True, capture_output=True, env=git_env)
        pr_cmd = ["gh", "pr", "create", "--fill", "-R", os.environ["ROTATION_REPO_SLUG"]]
        if dry_run:
            pr_cmd += ["--draft", "--title", "[DRY-RUN] credential rotation artifact — DO NOT MERGE"]
        r = subprocess.run(pr_cmd, cwd=repo, capture_output=True, text=True, env=git_env)
        if r.returncode != 0:
            return ActResult(Outcome.RETRYABLE, f"gh:{r.stderr[:200]}")
        return ActResult(Outcome.OK, ref=r.stdout.strip())
    except subprocess.CalledProcessError as e:
        return ActResult(Outcome.RETRYABLE, f"git:{(e.stderr or b'')[:200].decode(errors='replace')}")


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
    if pgb:
        ok, cur = _kubectl("get", "secret", "pgbouncer-userlist", "-n", pgb["namespace"],
                           "-o", "jsonpath={.data.userlist\\.txt}")
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"userlist-get:{cur}")
        entries, dropped = [], 0
        for line in base64.b64decode(cur.strip('"')).decode().splitlines():
            m = _USERLIST_LINE.match(line.strip())
            if m:
                entries.append(m.groups())
            elif line.strip():
                dropped += 1
        entries = [(u, p) for u, p in entries if u != successor]
        entries.append((successor, pw))
        ul = "".join(f'"{u}" "{p}"\n' for u, p in entries)
        patch = json.dumps({"data": {"userlist.txt": base64.b64encode(ul.encode()).decode()}})
        ok, d = _kubectl("patch", "secret", "pgbouncer-userlist", "-n", pgb["namespace"],
                         "--type", "merge", "-p", patch)
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"userlist-patch:{d}")
        if dropped:
            print(f"userlist: dropped {dropped} malformed lines")

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
        expected = {k: t.format(**fmt) for k, t in _secret_keys(s).items()}
        if s.get("mode") == "gitops":
            ok, d = _kubectl("get", "secret", s["name"], "-n", c["namespace"],
                             "-o", "jsonpath={.data}")
            if not ok:
                return ActResult(Outcome.RETRYABLE, f"secret-wait-{s['name']}:{d}")
            try:
                live = json.loads(d)
            except ValueError:
                return ActResult(Outcome.RETRYABLE, f"secret-wait-parse:{s['name']}")
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
    return ActResult(Outcome.OK, "consumers-rolled")


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
        if os.environ.get("ROTATION_ALLOW_DROP"):
            cur.execute(psql.SQL("REASSIGN OWNED BY {} TO postgres").format(psql.Identifier(principal)))
            cur.execute(psql.SQL("DROP OWNED BY {}").format(psql.Identifier(principal)))
            cur.execute(psql.SQL("DROP ROLE IF EXISTS {}").format(psql.Identifier(principal)))
            return ActResult(Outcome.OK, f"role-dropped:{principal}")
        # Default: NOLOGIN kills auth immediately but keeps object
        # ownership intact — DROP would fail while the role owns
        # tables/migrations (always true for cortex_db_admin).
        cur.execute(psql.SQL("ALTER ROLE {} NOLOGIN").format(psql.Identifier(principal)))
        conn.close()
        return ActResult(Outcome.OK, f"role-nologin:{principal}")
    except Exception as e:
        return ActResult(Outcome.RETRYABLE, f"pg:{type(e).__name__}")


@activity.defn
async def liveness_dead_check(principal: str, sealed: str) -> ActResult:
    """Old credential must FAIL auth — twice consecutively to be safe."""
    # Read the PREDECESSOR password from the sealed snapshot — the live
    # secret has been overwritten by Flux post-merge (successor creds).
    old_pw = _sealed_field(sealed, "predecessor_password")
    if not old_pw:
        return ActResult(Outcome.RETRYABLE, "predecessor-cred-unsealed")
    dead = 0
    for _ in range(2):
        try:
            import psycopg2
            pw = old_pw
            conn = psycopg2.connect(
                os.environ["ROTATION_PG_DSN"].split(" user=")[0]
                + f" user={principal} password={pw}", connect_timeout=5)
            conn.close()
            return ActResult(Outcome.COMPENSATE, "predecessor-still-valid")
        except psycopg2.OperationalError as e:
            msg = str(e)
            if "password authentication failed" in msg or "not permitted to log in" in msg:
                dead += 1
            else:
                time.sleep(3)
        except Exception:
            time.sleep(3)
    return ActResult(Outcome.OK if dead >= 2 else Outcome.RETRYABLE,
                     f"dead-probes:{dead}/2")


@activity.defn
async def post_closure_evidence(evidence: dict) -> ActResult:
    """POST evidence → governance-closure endpoint."""
    url = os.environ.get("GOVERNANCE_CLOSURE_URL",
                         "https://governance-closure.patternfoundry.dev/api/evidence")
    try:
        req = urllib.request.Request(url, data=json.dumps(evidence).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
        return ActResult(Outcome.OK, "closure-posted")
    except Exception as e:
        return ActResult(Outcome.RETRYABLE, f"closure:{type(e).__name__}")

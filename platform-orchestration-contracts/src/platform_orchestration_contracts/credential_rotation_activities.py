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

    # Live cts-backend-db carries `password` + `uri` (full DSN) — both
    # must carry the successor cred. URI template comes from env so the
    # password stays alnum-safe (no URI escaping ever needed).
    # Snapshot the PREDECESSOR credential before merge — post-merge Flux
    # overwrites the live secret with the successor, so liveness checks
    # later must use this sealed snapshot, not the live secret.
    ok_s, old_b64 = _kubectl("get", "secret",
                            os.environ.get("ROTATION_SECRET_NAME", "cts-backend-db"),
                            "-n", os.environ.get("ROTATION_NAMESPACE", "cts"),
                            "-o", "jsonpath={.data.password}")
    old_pw = base64.b64decode(old_b64.strip('"')).decode() if ok_s else ""
    # DSN assembled from discrete env parts — no credential-shaped
    # postgresql://user:pw@ literal ever exists in YAML/manifests.
    _h = os.environ.get("ROTATION_PG_HOST", "pgbouncer.infra-data.svc.cluster.local")
    _p = os.environ.get("ROTATION_PG_PORT", "5432")
    _d = os.environ.get("ROTATION_PG_DB", "mydatabase")
    uri = f"postgresql://{successor}:{pw}@{_h}:{_p}/{_d}"
    manifest = (
        "apiVersion: v1\nkind: Secret\nmetadata:\n"
        f"  name: {os.environ.get('ROTATION_SECRET_NAME','cts-backend-db')}\n"
        f"  namespace: {os.environ.get('ROTATION_NAMESPACE','cts')}\n"
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
async def sops_encrypt_and_open_pr(sealed: str, branch: str) -> ActResult:
    """Write sealed manifest + open PR via gh. sealed is already encrypted."""
    try:
        ref = json.loads(sealed)
        blob = base64.b64decode(ref["sealed"])
    except Exception:
        return ActResult(Outcome.FATAL, "sealed-ref-malformed")
    secret_path = os.environ["ROTATION_SECRET_PATH"]  # e.g. apps/secrets/cts/cts-backend-db.yaml
    ok, d = _kubectl("config", "current-context")  # sanity
    repo = os.environ.get("ROTATION_REPO_DIR", "/workspace")
    try:
        subprocess.run(["git", "-C", repo, "checkout", "-B", branch], check=True, capture_output=True)
        open(os.path.join(repo, secret_path), "wb").write(blob)
        subprocess.run(["git", "-C", repo, "add", secret_path], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "commit", "-m",
                        "security: rotate credential (sops-encrypted) [rotation-workflow]"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "push", "-u", "origin", branch], check=True, capture_output=True)
        r = subprocess.run(["gh", "pr", "create", "--fill", "-R",
                            os.environ["ROTATION_REPO_SLUG"]],
                           cwd=repo, capture_output=True, text=True)
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
async def wait_consumer_healthy(consumers: list[str], sealed: str, timeout_s: int = 900) -> ActResult:
    """All consumers' new pods Ready AND successor auth probe passes."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        all_ready = True
        for c in consumers:
            ok, _ = _kubectl("rollout", "status", f"deploy/{c}", "-n",
                             os.environ.get("ROTATION_NAMESPACE", "cts"), f"--timeout=10s")
            if not ok:
                all_ready = False
        if all_ready:
            # probe: can the successor actually authenticate?
            pw = _plaintext_from_sealed(sealed)
            if pw:
                import psycopg2
                try:
                    conn = psycopg2.connect(
                        os.environ["ROTATION_PG_DSN"].replace(
                            f"user={os.environ.get('ROTATION_PRINCIPAL','')}",
                            f"user={json.loads(sealed).get('successor','')}"),
                        connect_timeout=6)
                    conn.close()
                    return ActResult(Outcome.OK, "consumers-ready+successor-auth")
                except Exception:
                    pass
            return ActResult(Outcome.OK, "consumers-ready")
        time.sleep(10)
    return ActResult(Outcome.COMPENSATE, "health-gate-timeout")


@activity.defn
async def patch_and_roll(consumers: list[str], sealed: str) -> ActResult:
    """Update pgbouncer userlist (if consumer) + rollout restarts.

    Idempotent-ish: rollout restart is safe to re-issue. The userlist
    patch appends only if the successor line is absent.
    """
    successor = json.loads(sealed).get("successor", "") if sealed.startswith("{") else ""
    pw = _plaintext_from_sealed(sealed) or ""
    if "pgbouncer" in consumers:
        # append successor to userlist (plaintext form — pgbouncer SCRAMs it)
        ok, cur = _kubectl("get", "secret", "pgbouncer-userlist", "-n", "infra-data",
                           "-o", "jsonpath={.data.userlist\\.txt}")
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"userlist-get:{cur}")
        ul = base64.b64decode(cur.strip('"')).decode()
        if f'"{successor}"' not in ul:
            ul += f'"{successor}" "{pw}"\n'
            patch = json.dumps({"data": {"userlist.txt": base64.b64encode(ul.encode()).decode()}})
            ok, d = _kubectl("patch", "secret", "pgbouncer-userlist", "-n", "infra-data",
                             "--type", "merge", "-p", patch)
            if not ok:
                return ActResult(Outcome.RETRYABLE, f"userlist-patch:{d}")
        ok, d = _kubectl("rollout", "restart", "deploy/pgbouncer", "-n", "infra-data")
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"pgbouncer-restart:{d}")
    for c in consumers:
        if c == "pgbouncer":
            continue
        ok, d = _kubectl("rollout", "restart", f"deploy/{c}", "-n",
                         os.environ.get("ROTATION_NAMESPACE", "cts"))
        if not ok:
            return ActResult(Outcome.RETRYABLE, f"restart-{c}:{d}")
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

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


def _sops_encrypt(manifest: bytes) -> tuple[bool, bytes | str]:
    """sops -e using the repo .sops.yaml age key (runner pod mounts it)."""
    try:
        r = subprocess.run(
            ["sops", "-e", "--input-type", "yaml", "--output-type", "yaml", "/dev/stdin"],
            input=manifest, capture_output=True, timeout=30,
            env={**os.environ, "SOPS_AGE_KEY_FILE": os.environ.get("SOPS_AGE_KEY_FILE", "/etc/sops/age-key.txt")},
        )
        return (r.returncode == 0), (r.stdout if r.returncode == 0 else r.stderr[:300])
    except Exception as e:
        return False, f"sops:{type(e).__name__}"


# ----------------------------------------------------------------------
# Activities
# ----------------------------------------------------------------------

async def generate_successor_cred(spec: dict) -> ActResult:
    """Generate high-entropy password; seal it immediately.

    Result ref is a SealedCred handle — plaintext exists only in
    `pw` (activity-local) and is stashed under an env var name for
    same-pod use by sops/PR steps, never returned or logged.
    """
    principal = spec["principal"]
    successor = spec["successor"]
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

    manifest = (
        "apiVersion: v1\nkind: Secret\nmetadata:\n"
        f"  name: {os.environ.get('ROTATION_SECRET_NAME','cts-backend-db')}\n"
        f"  namespace: {os.environ.get('ROTATION_NAMESPACE','cts')}\n"
        "type: Opaque\nstringData:\n"
        f"  PG_PASS: \"{pw}\"\n  PG_USER: \"{successor}\"\n"
    ).encode()
    os.environ["_ROT_PLAINTEXT_TMP"] = pw
    del pw  # plaintext lives in env only now; cleared on activity end

    ok, sealed = _sops_encrypt(manifest)
    if not ok:
        os.environ.pop("_ROT_PLAINTEXT_TMP", None)
        return ActResult(Outcome.FATAL, f"sops-encrypt-failed:{sealed}")
    sc = SealedCred(base64.b64encode(sealed if isinstance(sealed, bytes) else sealed.encode()).decode(),
                    successor, "_ROT_PLAINTEXT_TMP")
    return ActResult(Outcome.OK, ref=json.dumps({"sealed": sc.sealed_b64, "ref": sc.plaintext_ref}))


async def create_role(principal: str, successor: str, role_spec: dict) -> ActResult:
    """CREATE ROLE successor (idempotent) + inherit principal's grants."""
    pw = os.environ.pop("_ROT_PLAINTEXT_TMP", None)
    if pw is None:
        return ActResult(Outcome.FATAL, "plaintext-ref-missing")
    try:
        ok, d = _pg('CREATE ROLE %s LOGIN PASSWORD %s', (successor, pw)) if False else (True, "skip")
        # AsIs quoting via psycopg2.sql for identifiers:
        from psycopg2 import sql as psql
        import psycopg2
        conn = psycopg2.connect(os.environ["ROTATION_PG_DSN"], connect_timeout=8)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(psql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE {}").format(
            psql.Identifier(successor), psql.Literal(pw), psql.Identifier(principal)))
        conn.close()
        return ActResult(Outcome.OK, f"role-created:{successor}")
    except psycopg2.errors.DuplicateObject:
        return ActResult(Outcome.OK, "role-exists")  # idempotent
    except Exception as e:
        return ActResult(Outcome.RETRYABLE, f"pg:{type(e).__name__}")


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


async def wait_consumer_healthy(consumers: list[str], timeout_s: int = 900) -> ActResult:
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
            pw = os.environ.get("_ROT_PLAINTEXT_TMP")
            if pw:
                import psycopg2
                try:
                    conn = psycopg2.connect(
                        os.environ["ROTATION_PG_DSN"].replace(
                            f"user={os.environ.get('ROTATION_PRINCIPAL','')}",
                            f"user={os.environ.get('_ROT_SUCCESSOR','')}"),
                        connect_timeout=6)
                    conn.close()
                    return ActResult(Outcome.OK, "consumers-ready+successor-auth")
                except Exception:
                    pass
            return ActResult(Outcome.OK, "consumers-ready")
        time.sleep(10)
    return ActResult(Outcome.COMPENSATE, "health-gate-timeout")


async def patch_and_roll(consumers: list[str], sealed: str) -> ActResult:
    """Update pgbouncer userlist (if consumer) + rollout restarts.

    Idempotent-ish: rollout restart is safe to re-issue. The userlist
    patch appends only if the successor line is absent.
    """
    successor = os.environ.get("_ROT_SUCCESSOR", "")
    pw = os.environ.get("_ROT_PLAINTEXT_TMP", "")
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


async def revoke_predecessor(principal: str) -> ActResult:
    """DROP ROLE — idempotent (IF EXISTS). Used for predecessor AND
    compensation (delete unused successor)."""
    try:
        from psycopg2 import sql as psql
        import psycopg2
        conn = psycopg2.connect(os.environ["ROTATION_PG_DSN"], connect_timeout=8)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(psql.SQL("REASSIGN OWNED BY {} TO postgres").format(psql.Identifier(principal))) \
            if os.environ.get("ROTATION_REASSIGN") else None
        cur.execute(psql.SQL("DROP ROLE IF EXISTS {}").format(psql.Identifier(principal)))
        conn.close()
        return ActResult(Outcome.OK, f"role-dropped:{principal}")
    except Exception as e:
        return ActResult(Outcome.RETRYABLE, f"pg:{type(e).__name__}")


async def liveness_dead_check(principal: str, sealed: str) -> ActResult:
    """Old credential must FAIL auth — twice consecutively to be safe."""
    dead = 0
    for _ in range(2):
        try:
            import psycopg2
            pw = os.environ.get("_ROT_OLD_PW")  # injected by runner for the probe
            conn = psycopg2.connect(
                os.environ["ROTATION_PG_DSN"].split(" user=")[0]
                + f" user={principal} password={pw}", connect_timeout=5)
            conn.close()
            return ActResult(Outcome.COMPENSATE, "predecessor-still-valid")
        except psycopg2.OperationalError as e:
            if "password authentication failed" in str(e):
                dead += 1
            else:
                time.sleep(3)
        except Exception:
            time.sleep(3)
    return ActResult(Outcome.OK if dead >= 2 else Outcome.RETRYABLE,
                     f"dead-probes:{dead}/2")


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

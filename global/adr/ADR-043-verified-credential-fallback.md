# ADR-043: Verified Credential Resolution for Platform Storage Clients

* **Status**: Proposed
* **Date**: 2026-11-14
* **Decides**: How long-lived application processes resolve object-storage credentials when the environment may carry stale-but-present values after credential rotation
* **Related**: ADR-037 (Credential Rotation Lifecycle Workflow), ADR-038 (Credential Discovery, Inventory, and Enrollment Standard), ADR-015 (Resource Resolution Priority Framework)

---

## 1. Context & Problem Statement

Credential rotation is now a live operational pipeline (ADR-037). It rotates
service-account keys in Kubernetes Secrets on a schedule. Long-lived
application processes — Streamlit dashboards, daemon reconcilers, ad-hoc CLIs —
commonly source the same credentials from environment variables or local
`.env` / SOPS-encrypted files that are **not** rotated in lockstep.

The result is a specific, misdiagnosable failure class:

> A credential that is **present but stale** is worse than one that is
> absent. Presence wins every `or`-chain and config default, then fails
> authentication at first use — and the failure surfaces far from its
> cause, usually as missing features rather than an auth error.

Observed instance (2026-11-14, `neural_mesh_canvas`): the credential rotation
swapped the MinIO service account. `voice_registry.py` resolved
`PLATFORM_STORAGE_ACCESS_KEY`/`SECRET_KEY` from environment only — every
registry call raised `InvalidAccessKeyId`, a `try/except` in the pack editor
swallowed it to `[]`, and the voice multiselect silently collapsed to the
stock `[female, male]` options. Casting listings kept working because the
app's own client had a naive env-else-secret fallback — which masks the same
bug whenever the stale env value is *nonempty*. Meanwhile the casting
reconciler's SOPS launcher failed outright because its indexed secret key
had been removed in the secret-management move.

Three distinct consumers, three different failure shapes, one root cause:
**credential source-of-truth had moved, and presence was treated as
sufficient proof of validity.**

## 2. Decision

Platform storage clients resolve credentials by **verified resolution**,
not static precedence:

1. **Candidate order**: environment (`PLATFORM_STORAGE_*`, then `MINIO_*`),
   then the live Kubernetes Secret (`tts-storage-creds`, `temporal` ns —
   the same object the consuming workloads mount).
2. **Verify before trusting**: an env-sourced pair is exercised once with a
   cheap probe (`list_objects_v2(MaxKeys=1)`) at client construction. It is
   adopted only if the probe succeeds.
3. **Auth failures degrade, others propagate**: if the probe fails with an
   authentication-class error (`InvalidAccessKeyId`,
   `SignatureDoesNotMatch`, `InvalidToken`, `ExpiredToken`, `AccessDenied`),
   resolution falls through to the Kubernetes Secret. Non-auth failures
   (unreachable, throttled, DNS) propagate unchanged — they are not a
   credential problem, and masking them would hide real outages.
4. **Lazy, process-scoped caching**: resolution runs on first client use,
   not at import, so library importers that never touch storage pay no
   probe cost. The resolved pair is cached for the process lifetime —
   rotation mid-flight is an operator event, not a silent drift (a
   subsequent rotation surfaces errors rather than silently re-resolving
   under a different identity).
5. **Fail-closed absence**: when neither source yields a pair, calls fail
   with the auth error — no unsigned or stock-credential fallback.

### Reference shape

```python
def _resolve_client():
    ak = os.getenv("PLATFORM_STORAGE_ACCESS_KEY") or os.getenv("MINIO_ACCESS_KEY") or ""
    sk = os.getenv("PLATFORM_STORAGE_SECRET_KEY") or os.getenv("MINIO_SECRET_KEY") or ""
    if ak and sk:
        c = _build_client(ak, sk)
        try:
            c.list_objects_v2(Bucket=BUCKET, MaxKeys=1)
            return c                      # env pair proven live
        except ClientError as e:
            if e.response["Error"]["Code"] not in _AUTH_ERRS:
                raise                     # not a creds problem — surface it
    return _build_client(_k8s_secret(NAME, AK_KEY),
                         _k8s_secret(NAME, SK_KEY))
```

## 3. Rationale

- **Presence ≠ validity.** Static precedence (`env or secret`) was designed
  for a world where env was authoritative. Rotation inverts that: the live
  source is the cluster Secret, env is a convenience that decays.
- **Verification is cheap.** One `MaxKeys=1` listing per process lifetime.
- **Auth-aware, not error-swallowing.** Only authentication-class failures
  trigger fallback; transport and permission surprises still surface.
- **kubectl is already a dev-runtime dependency** in the environments where
  these tools run; in-cluster consumers mount the Secret natively and never
  reach the fallback path (env is set by the workload spec and probes true).

## 4. Alternatives Considered

| Option | Rejected because |
|---|---|
| Naive `env or k8s-secret` precedence | Stale-but-nonempty env still wins; the exact failure observed |
| Sync `.env`/SOPS to rotation output | Duplicates the credential; another artifact to keep secret-scanned and rotate-aware |
| Fetch from Kubernetes on every call | Prohibitively chatty; k8s API becomes a hard dependency per request |
| IRSA / token refresh sidecars | Right long-term shape, but a platform change; this ADR is the application-side contract that remains correct underneath it |
| Process restart on rotation | Acceptable but requires every consumer to add restart hooks; verification achieves the same correctness locally |

## 5. Consequences

**Positive**
- Stale env credentials self-heal to the live Secret — the symptom class
  (features silently collapsing to stock behavior) is eliminated at the
  source.
- One pattern, applied identically across `casting_call_app.py`,
  `voice_registry.py`, and future storage clients; the probe makes
  "which credential am I actually using" observable and testable.

**Negative / accepted**
- First storage call in a process pays one listing + (worst case) one
  `kubectl` invocation (~100–300 ms).
- Resolution order gives a *graceful* degradation, which can obscure that
  env creds are stale. Consumers SHOULD log which source was resolved once
  at startup; silent divergence between processes is a provenance smell.
- `kubectl` binary + kubeconfig access is required on dev hosts — already
  true for the tooling that uses this pattern.

**Follow-ons**
- `casting_reconciler.py` and other launch-context daemons should adopt the
  same resolution (currently env-at-launch only; `reconciler-start.sh`
  already sources the live Secret, which is the bootstrap-level equivalent).
- When ADR-037 rotation gains standard consumer-restart hooks, this pattern
  becomes the belt under that suspenders — it degrades gracefully during
  the gap between Secret update and consumer restart.

## 6. Compliance & Validation

- Verified live 2026-11-14: stale env pair injected → probe rejected →
  `tts-storage-creds` adopted → `list_objects_v2` succeeds; 102 registry
  voices resolve in the app.
- Gitleaks discipline unchanged: the Secret value never enters files, logs,
  or test fixtures; tests stub the resolution boundary, not the secret.

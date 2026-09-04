# ADR-035 Dependency: Git & PR Status Audit

* **Date**: 2026-09-04
* **Audits**: Git state of every system ADR-035 depends on
* **Purpose**: Determine what is committed, pushed, in PR, or stranded in local working trees before implementation begins

---

## Summary

| # | Component | Repo | Branch | Committed? | Pushed? | In PR? | Risk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | CTS Temporal pilot (`src/temporal_pilot/`) | AttunementWeaver | `security/comprehensive-secret-remediation` | **No — untracked** | No | **No** | **Critical** |
| 2 | CTS `api_server.py` Temporal routing (+152 lines) | AttunementWeaver | same | **No — uncommitted modifications** | No | **No** | **Critical** |
| 3 | CTS pilot canary script + DLQ migration + tests | AttunementWeaver | same | **No — untracked** | No | **No** | **High** |
| 4 | CTS `deploy-dev.yaml` sidecar manifest | AttunementWeaver | same | Yes (in PR #1) | Yes | **PR #1 (open)** | Low |
| 5 | Sidecar env vars (`GPU_NANNY_*`, `OLLAMA_HOST`) | AttunementWeaver | same | **Not present in committed manifest** | — | — | **Medium** (ADR-035 step 1) |
| 6 | GPU Nanny controller | infrastructure | `fix/manifest-validation-empty-diff` | Yes | Yes | PR #93 (open, unrelated) | Low |
| 7 | Ollama deployment patch (`shared-infra/ollama-patch.yaml`) | infrastructure | same | Yes | Yes | Not in PR #93 | Low |
| 8 | ADR-035 itself | AI_AGENTS | `main` | **No — untracked** | No | **No** | Medium |

**Bottom line**: The two most critical dependencies — the entire CTS Temporal pilot codebase and the api_server.py routing integration — are **uncommitted and exist only in the local working tree**. They are not in PR #1, not pushed, and not on any remote branch. If this working tree is lost, the pilot implementation is lost.

---

## Detailed Findings

### 1. CTS Temporal pilot (`src/temporal_pilot/`) — CRITICAL: untracked

- **Repo**: `git@github.com:arch-pattern-backup/AttunementWeaver.git` (CTS)
- **Branch**: `security/comprehensive-secret-remediation`
- **Local HEAD**: `49dc80b` (matches PR #1 head)
- **Git status**: `?? src/temporal_pilot/` — the entire directory is untracked
- **Remote check**: `git ls-tree -r origin/security/comprehensive-secret-remediation` — no `temporal_pilot` files on remote
- **PR #1 check**: `gh pr view 1 --json files` — no `temporal_pilot` files in the PR
- **Any branch**: `git log --all --oneline -- src/temporal_pilot/` — empty; never committed on any branch
- **Stash**: none

**Files stranded in working tree**:
```
src/temporal_pilot/__init__.py
src/temporal_pilot/completeness.py
src/temporal_pilot/DEPLOYMENT.md
src/temporal_pilot/dlq.py
src/temporal_pilot/dlq_replay.py
src/temporal_pilot/routing.py
src/temporal_pilot/terminal_record.py
src/temporal_pilot/worker.py
src/temporal_pilot/workflow.py
```

This is the complete Temporal pilot: workflow, worker, routing (idempotent acceptance), DLQ, completeness predicate, and terminal record enforcement. **All of it is uncommitted.**

### 2. CTS `api_server.py` Temporal routing — CRITICAL: uncommitted modifications

- **File**: `src/ingestion/api_server.py` (tracked file)
- **Git status**: `M src/ingestion/api_server.py` — 152 insertions, 2 deletions
- **In PR #1?**: No — PR #1 does not include `api_server.py`
- **Diff content**: The +152 lines add the Temporal pilot routing integration:
  - `from src.temporal_pilot.routing import is_pilot_job, submit_to_temporal`
  - Pilot job detection via `is_pilot_job(req.source_type)`
  - Submission to Temporal via `submit_to_temporal()`
  - Requeue path routing for pilot jobs
  - DLQ entry creation on submission failure (`from src.temporal_pilot.dlq import write_submission_failure`)
  - Queue worker skip logic for pilot jobs (`source_type != 'cts_temporal_pilot'`)

This is the glue that routes jobs from the API server into the Temporal workflow. **It is uncommitted and not in any PR.**

### 3. CTS pilot canary script, DLQ migration, tests — HIGH: untracked

- **Git status**: all `??` (untracked)
- **Files**:
  ```
  ?? scripts/launch_temporal_pilot_canary.sh
  ?? src/database/migrations/versions/c3d4e5f6a7b8_add_temporal_submission_dlq.py
  ?? tests/test_completeness.py
  ?? tests/test_terminal_record.py
  ```
- **In PR #1?**: No

These are operational and test artifacts for the pilot. The canary script is needed to launch pilot jobs; the migration adds the DLQ table; the tests validate the completeness predicate and terminal record enforcement.

### 4. CTS `deploy-dev.yaml` sidecar manifest — in PR #1

- **Git status**: `M deploy-dev.yaml` (working tree has +2 label lines vs HEAD)
- **Committed version** (in PR #1): contains the sidecar container definitions:
  - `cts-temporal-worker` container: `command: ["python3", "-m", "src.temporal_pilot.worker"]`
  - `cts-dlq-replay` container: `command: ["python3", "-m", "src.temporal_pilot.dlq_replay"]`
  - `CTS_TEMPORAL_PILOT_ENABLED: "false"` (env var on main container)
- **PR #1**: includes `deploy-dev.yaml` (the committed version with sidecar config)
- **Working-tree diff**: only +2 lines (Ingress labels), unrelated to the pilot

The sidecar manifest is committed and in the PR. However, the sidecar **references `src.temporal_pilot.worker`** which is untracked (finding #1) — so the deployed image would fail to start the sidecar if the code isn't baked into the image.

### 5. Sidecar env vars gap — MEDIUM: not in committed manifest

- **Committed `deploy-dev.yaml`** sidecar (`cts-temporal-worker` container) env vars:
  ```
  TEMPORAL_HOST, TEMPORAL_NAMESPACE, POSTGRES_DSN,
  WHISPER_API_URL, WHISPER_MODEL,
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION, AWS_ENDPOINT_URL_S3
  ```
- **Missing** (per ADR-035 step 1):
  ```
  GPU_NANNY_HOST, GPU_NANNY_PORT, OLLAMA_HOST
  ```
- **Confirmed**: `git show HEAD:deploy-dev.yaml` — grep for `GPU_NANNY`/`OLLAMA_HOST` in the sidecar section returns nothing.

This is the env-var gap ADR-035 step 1 addresses. The main `cts-backend` container has these vars; the sidecar does not.

### 6. GPU Nanny controller — LOW: committed, no modifications

- **Repo**: `git@github.com:architect-patternfoundry-systems/infrastructure.git`
- **Branch**: `fix/manifest-validation-empty-diff` (PR #93, open)
- **Local HEAD**: `1549c35` (matches PR #93 head)
- **Git status**: `gpu-nanny-controller/` — no modifications
- **Files tracked**: `gpu-nanny-controller/base/gpu_nanny_controller.py`, `deployment.yaml`, `kustomization.yaml`, `rbac.yaml`, `service.yaml`, `servicemonitor.yaml`, etc.
- **Deployment image**: `registry-bridge.tailc2cafc.ts.net/gpu-nanny-controller:20260620220400-cts-ollama`
- **PR #93**: open, but is about CI manifest validation — unrelated to the nanny. The nanny files were committed in prior merged commits.

The GPU Nanny controller (including Ollama lease management and `SERVICE_CONFIGS["ollama"]`) is committed and deployed. No action needed.

### 7. Ollama deployment patch — LOW: committed, no modifications

- **File**: `shared-infra/ollama-patch.yaml` (tracked, no modifications)
- **Content**: Kustomize strategic merge patch for the Ollama deployment (image, command, env, hostPath volumes)
- **Note**: The `replicas: 0` state is a **live cluster state** (manual scale-down), not a manifest issue. The manifest does not declare `replicas: 0` — the `last-applied-configuration` annotation shows `replicas: 1`. The scale-down was done via `kubectl scale` or the nanny, not via Git.

### 8. ADR-035 itself — MEDIUM: untracked

- **Repo**: `https://github.com/architect-patternfoundry-systems/AI_AGENTS.git`
- **Branch**: `main` (up to date with remote: 0 ahead, 0 behind)
- **Git status**: `?? global/adr/ADR-035-cts-temporal-ollama-lease-wiring.md` — untracked
- **In PR?**: No (the only open AI_AGENTS PR is #1 for ADR-030, unrelated)
- **Note**: Many other ADRs are also untracked in this repo (ADR-016 variants, 018-022, 026-027, 031). This appears to be a known state — the AI_AGENTS repo has a large backlog of untracked governance docs.

---

## Risk Assessment

### Critical risk: pilot code is stranded

The entire CTS Temporal pilot implementation — workflow, worker, routing, DLQ, completeness, terminal record, tests, canary script, and the api_server.py routing integration — exists **only in the local working tree** on branch `security/comprehensive-secret-remediation`. It is:

- Not committed to the branch
- Not pushed to the remote
- Not in PR #1 (which is on the same branch but only contains secret-remediation files)
- Not on any other branch
- Not in any stash

If the working tree is lost (disk failure, accidental `git clean`, branch deletion), the pilot implementation is gone. This violates the **No Abandoned Stashes** rule in the workspace AGENTS.md: *"Work must be committed to an explicit branch or referenced in ARTIFACTS.md."*

### Deployment coherence risk

The `deploy-dev.yaml` sidecar manifest (committed in PR #1) references `src.temporal_pilot.worker` and `src.temporal_pilot.dlq_replay`, but the code those commands import is untracked. If PR #1 is merged and deployed without the pilot code being committed and baked into the image, the sidecar containers will crash on startup with `ModuleNotFoundError`.

### Recommended actions before implementing ADR-035

1. **Commit the pilot code** to the `security/comprehensive-secret-remediation` branch (or a dedicated `feature/cts-temporal-pilot` branch) and push. This includes:
   - `src/temporal_pilot/` (all 9 files)
   - `src/ingestion/api_server.py` (the +152 line routing integration)
   - `scripts/launch_temporal_pilot_canary.sh`
   - `src/database/migrations/versions/c3d4e5f6a7b8_add_temporal_submission_dlq.py`
   - `tests/test_completeness.py`
   - `tests/test_terminal_record.py`

2. **Open a PR for the pilot code** (or add it to PR #1 if appropriate). The pilot code and the secret-remediation work are on the same branch but serve different purposes — a dedicated branch/PR for the pilot may be cleaner.

3. **Commit ADR-035** to the AI_AGENTS repo and push.

4. **Then proceed with ADR-035 implementation** (sidecar env vars, enrich_optional lease wiring, pilot enablement).

---

## Repository Reference

| Repo | Remote | Current Branch | PR |
| :--- | :--- | :--- | :--- |
| CTS (AttunementWeaver) | `git@github.com:arch-pattern-backup/AttunementWeaver.git` | `security/comprehensive-secret-remediation` | #1 (open, secret remediation only) |
| Infrastructure | `git@github.com:architect-patternfoundry-systems/infrastructure.git` | `fix/manifest-validation-empty-diff` | #93 (open, CI manifest validation) |
| AI_AGENTS | `https://github.com/architect-patternfoundry-systems/AI_AGENTS.git` | `main` | #1 (open, ADR-030, unrelated) |

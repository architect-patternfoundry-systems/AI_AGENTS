# ADR-035: CTS Temporal Pilot — Ollama Lease Wiring for On-Demand Scale-Up

* **Status**: Accepted, implementation gated
* **Date**: 2026-09-04
* **Decides**: How the CTS Temporal pilot workflow acquires Ollama GPU capacity on demand, with retry-safe lease lifecycle, explicit timeout budgets, and source-control preconditions
* **Amends**: ADR-020 (GPU Resource Arbitration and Scaling Paradigms)
* **Related**: ADR-015 (Resource Resolution Priority Framework), ADR-016 (Scale-to-Zero Transcription), ADR-028 (Service Delivery and Break-Glass Recovery Framework)
* **Companion**: `ADR-035-dependency-git-status.md` (source-control audit of all dependencies)

---

## 1. Context & Problem Statement

### 1.1 Incident

On 2026-09-04 the `attunement-weaver` (CTS backend) began emitting repeated
debug-level errors:

```
Ollama availability check failed: HTTPConnectionPool(
  host='ollama.shared-infra.svc.cluster.local', port=1434):
  Max retries exceeded ... [Errno 111] Connection refused
```

Investigation revealed the `ollama` Deployment in `shared-infra` is scaled to
**0 replicas** (`spec.replicas: 0`). The Service `ollama:1434` still exists,
so DNS resolves but no pods back it — hence `Connection refused`.

Key facts:
- The scale-down was **manual**. The `last-applied-configuration` annotation
  shows `replicas: 1`; the live spec is `0`.
- **No KEDA ScaledObject** governs Ollama — it is not autoscaled-to-zero by
  KEDA.
- Flux reconciliation is **explicitly disabled** on the Deployment
  (`kustomize.toolkit.fluxcd.io/reconcile: disabled`), so GitOps will not
  restore it.
- The `cortex` node has 4 GPUs, 2 allocated, **2 free** — capacity exists.
- The debug logs originate from `OllamaClient.check_available`, the cached
  probe used by the `/health` liveness check and startup hook. They are
  liveness-probe noise, not job-path failures. The job path uses
  `request_lease`, which triggers scale-up — but no job has triggered a
  scale-up recently.

### 1.2 Existing infrastructure (already built, partially deployed)

Three systems already exist that, when connected, provide on-demand GPU pod
scale-up for Temporal-routed CTS jobs:

**A. CTS Temporal pilot** (`cts/src/temporal_pilot/`)

A Temporal workflow `CTSTranscriptWorkflow` orchestrates: download → chunk →
transcribe → merge → enrich(optional), with a completeness predicate and
exactly-one terminal record enforcement. A worker sidecar
(`cts-temporal-worker`) and DLQ replay sidecar (`cts-dlq-replay`) are
defined in the deployment manifest.

Workflow ID reuse policy: `submit_to_temporal` starts the workflow with
`id=job_id` and `id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE`.
This enforces at most one workflow execution for a CTS job ID within the
Temporal Namespace retention window. This protects against duplicate starts,
including starts after a prior execution has closed — regardless of whether
that execution completed, failed, timed out, was cancelled, or terminated.

**Consequences of `REJECT_DUPLICATE` that must be accounted for:**
- A failed pilot job **cannot be replayed** under the same `job_id` by
  starting a fresh workflow.
- A corrected input **cannot be processed** under the same `job_id`.
- Operational re-drive needs either a new CTS job ID, a deliberate Temporal
  reset/retry mechanism, or a domain-level attempt/version identifier
  distinct from the base CTS job ID.
- The policy only applies to **starting a workflow**. It does not make
  individual Activity attempts or external LLM calls safe by itself.
  Activity implementations must independently be retry-safe because Temporal
  may retry an Activity after a timeout, worker failure, or transient error.

Routing is gated by `CTS_TEMPORAL_PILOT_ENABLED` (currently `false`) and
triggered by `source_system = "cts_temporal_pilot"`. Only pilot-tagged jobs
use Temporal; all others stay on the existing DB-queue + subprocess pipeline.

**B. GPU Nanny lease system** (`apps/gpu-nanny-controller/`)

Per ADR-020, GPU-bound workloads must acquire a lease before execution. The
GPU Nanny controller manages `shared-infra/ollama` via
`SERVICE_CONFIGS["ollama"] = {deploy: ollama, ns: shared-infra, vram_mb: 4000}`
and provides an idempotent `scale_deployment()` with a guard that skips the
PATCH if already at the desired replica count.

CTS's `OllamaClient` (`api_server.py`) already implements the full lease
lifecycle for the non-Temporal job path:
1. `register_intent(job_id, service="ollama")` → nanny scales Ollama 0→1
2. `request_lease` → acquires a nanny lease (QUEUED → ADMITTED → ACTIVE)
3. Polls `/api/tags` until Ollama is ready (up to `OLLAMA_SCALE_UP_TIMEOUT=120s`)
4. `release_lease` → releases lease + clears intent → nanny scales back to 0

The nanny lease TTL for Ollama is `TTL_DEFAULTS["ollama"] = 300s`. Leases
expire automatically if not renewed; expired leases are reclaimable without
manual intervention.

**C. Existing Temporal worker patterns**

- `tts-temporal-worker` (temporal ns, running) — has `GPU_NANNY_URL` env from
  a ConfigMap, confirming Temporal workers already integrate with the nanny
  for GPU scale-up.
- `conflict-approval-worker` (temporal ns, running 36d) — another Python
  Temporal worker pattern.

### 1.3 The gap

The Temporal workflow's `enrich_optional` activity calls
`literary_intelligence.analyze_chunk`, which instantiates `ChatOllama`
directly against `OLLAMA_HOST`. **It does not acquire a GPU Nanny lease.**
When Ollama is scaled to zero, the enrichment activity hits
`Connection refused` and fails. The workflow degrades gracefully (enrichment
failure does not fail the workflow), but **no scale-up is ever triggered**
from the Temporal path.

Additionally, the `cts-temporal-worker` sidecar container is missing the env
vars needed to reach the nanny and Ollama (`GPU_NANNY_HOST`,
`GPU_NANNY_PORT`, `OLLAMA_HOST`). It only has `TEMPORAL_HOST`,
`TEMPORAL_NAMESPACE`, `POSTGRES_DSN`, `WHISPER_*`, `AWS_*`.

### 1.4 Source-control risk (from companion audit)

The entire CTS Temporal pilot codebase — `src/temporal_pilot/` (9 files),
the `api_server.py` routing integration (+152 lines), the DLQ migration,
tests, and canary script — is **uncommitted and exists only in the local
working tree** on branch `security/comprehensive-secret-remediation`. It is
not in PR #1, not pushed, not on any other branch, and not stashed. The
deployment manifest in PR #1 references `src.temporal_pilot.worker` and
`src.temporal_pilot.dlq_replay`, but the code those commands import is
untracked. If PR #1 is merged and deployed without the pilot code being
committed and baked into the image, the sidecar containers will crash on
startup with `ModuleNotFoundError`.

See `ADR-035-dependency-git-status.md` for the full audit.

---

## 2. Decision

The Temporal `enrich_optional` Activity will acquire an Ollama lease through
an activity-local client constructed by a shared `make_ollama_client()`
factory. The client will register intent, obtain and retain a specific
lease/ticket handle, wait for readiness within a bounded budget, invoke the
LLM, and idempotently release that specific handle from a `finally` path.
Expected availability failures will yield classified optional-enrichment
degradation after bounded retries; cancellation will propagate; unexpected
defects will remain observable and follow the explicit Temporal retry
policy. No pilot deployment, manifest merge, or enablement may occur until
the pilot source, tests, migration, canary, ADR, and deployable image are
committed, pushed, reviewed, and verified.

### 2.1 Activity-level lease acquisition with exception-safe cleanup

The `enrich_optional` activity must acquire an Ollama lease before invoking
the LLM, and release it in a `finally` block that covers all exit paths:
success, LLM exception, cancellation, and timeout.

```python
@activity.defn
async def enrich_optional(
    input: EnrichOptionalInput,
) -> EnrichOptionalOutput:
    client = make_ollama_client()
    lease = None
    lease_status = "failed"

    try:
        lease = await client.request_lease(input.job_id)
        if lease is None:
            lease_status = "degraded"
            return EnrichOptionalOutput(
                enriched=False,
                error="ollama_unavailable",
            )

        result = await analyze_chunk_with_ollama(input)
        lease_status = "complete"
        return EnrichOptionalOutput(
            enriched=True,
            conflicts_generated=result.conflicts_generated,
        )

    except asyncio.CancelledError:
        lease_status = "cancelled"
        raise

    except ExpectedOllamaFailure as exc:
        lease_status = "degraded"
        return EnrichOptionalOutput(
            enriched=False,
            error=classify_ollama_error(exc),
        )

    except Exception:
        lease_status = "failed"
        raise

    finally:
        if lease is not None:
            try:
                await client.release_lease(
                    lease_id=lease.ticket_id,
                    status=lease_status,
                )
            except Exception:
                logger.exception(
                    "Failed to release Ollama lease",
                    extra={
                        "job_id": input.job_id,
                        "lease_id": lease.ticket_id,
                        "lease_status": lease_status,
                    },
                )
```

Two details matter:
- `request_lease()` must return a lease object or ticket ID, rather than a
  Boolean, if it does not already. The existing `OllamaClient` already
  tracks `self.leases[job_id] = {"ticket_id": ...}` — the `ticket_id` is
  the release handle and should be used for release, not the `job_id` alone
  (see §5.1).
- Do **not** silently convert unexpected programming errors into graceful
  enrichment degradation. That would conceal defects. Allow bounded Temporal
  retries, then fail the Activity or degrade only via a consciously defined
  workflow policy. The `except Exception: raise` path above preserves this:
  unexpected errors propagate to Temporal's retry policy rather than being
  swallowed into a degraded result.

Intended semantics:
- `request_lease(job_id)` is idempotent for an Activity attempt/retry.
- `release_lease(lease_id, ...)` is idempotent and targets the specific
  acquired lease handle, not a job-level singleton.
- A failed cleanup must be observable and eventually reconciled by nanny
  TTL/reconciliation.
- A cleanup failure must not overwrite a successful enrichment result unless
  that is an intentional availability policy.
- The release status preserves a meaningful terminal lease state
  (`complete`, `degraded`, `cancelled`, or `failed`) — not unconditionally
  `status="complete"`.

### 2.2 Shared client factory

The API server constructs a module-level `ollama_client` singleton. The
Temporal worker sidecar runs in a separate process and does not share this
singleton. Importing the API-server module to obtain the singleton risks
importing API application initialization, mismatched configuration, and
side effects into the worker process.

A `make_ollama_client()` factory must be extracted into a shared module
that both the API server and the activity import. The factory constructs
the client from environment variables, not from the API-server singleton.

### 2.3 Sidecar environment variables and network access

The `cts-temporal-worker` sidecar container must receive the same
GPU-nanny and Ollama env vars as the main `cts-backend` container:

| Env var | Value |
| :--- | :--- |
| `GPU_NANNY_HOST` | `gpu-nanny-controller.toneroot.svc.cluster.local` |
| `GPU_NANNY_PORT` | `8081` |
| `OLLAMA_HOST` | `http://ollama.shared-infra.svc.cluster.local:1434` |

Copying environment variables does not guarantee network access. The
implementation must separately verify three distinct access layers:

**NetworkPolicy / DNS / service auth** (needed for sidecar → nanny/Ollama
HTTP calls):
- NetworkPolicies allow traffic from the `cts` namespace to
  `toneroot` (nanny) and `shared-infra` (Ollama).
- Service DNS resolves correctly from the sidecar.
- TLS/auth model (if any) for nanny and Ollama is satisfied.

**Kubernetes RBAC** (needed only if the sidecar invokes Kubernetes APIs
directly — e.g., if it reads Deployment status or patches replicas itself):
- The sidecar's ServiceAccount has the necessary Role/RoleBinding.
- The current design routes scale-up through the nanny, so the sidecar
  should **not** need Kubernetes API access. If it does, this is a design
  deviation that must be reviewed.

**Nanny controller RBAC** (needed for the nanny to patch the Ollama
Deployment and inspect the resources it governs):
- Already configured for the existing `gpu-nanny-controller` deployment.
- No change needed for this ADR unless the nanny's RBAC is scoped to
  specific namespaces that exclude `shared-infra`.

### 2.4 Activity retry and error taxonomy

The current workflow says enrichment "degrades gracefully" but does not
distinguish between failures that should be retried by Temporal and
failures that should immediately produce a degraded result. An explicit
error taxonomy is required:

| Failure class | Temporal behavior | Result behavior | Rationale |
| :--- | :--- | :--- | :--- |
| Nanny unavailable | Retry a small bounded number of times, then degrade | `enriched=False`, reason `nanny_unavailable` | A short controller outage may self-heal |
| Ollama cold-start/readiness timeout | Retry at most once or degrade immediately | `enriched=False`, reason `scale_up_timeout` | Avoid repeated long waits and GPU churn |
| Ollama 5xx/connection reset during inference | Bounded retry if request is safe to repeat | Otherwise degrade | Depends on whether inference has side effects |
| Invalid prompt/model/configuration | Non-retryable | `enriched=False`, reason `configuration_error` | Retrying cannot repair deterministic faults |
| Temporal cancellation | Propagate cancellation | Do not silently convert to success | Preserves workflow control-plane semantics |
| Unexpected programming error | Retry per bounded policy, then fail/degrade | Logged with correlation IDs | Avoids hiding implementation defects |

### 2.5 Enrichment side-effect idempotency

The current reviewed implementation of `enrich_optional` is **assumed** to
return enrichment output without persisting business results. This
assumption must be verified at implementation time by tracing all calls
below `analyze_chunk_with_ollama`. Any present or future external business
write — including conflict persistence, artifact creation, event
publication, or cache population — requires an idempotency key and
conflict-safe persistence semantics before retry is enabled.

The non-Temporal enrichment path in `cts_transcribe.py` **does write** to
`generated_conflicts.json` by appending conflict records without
deduplication. This confirms that the broader enrichment pattern has side
effects, and the Temporal activity must be verified not to share that
behavior unless idempotency is explicitly addressed.

If an idempotency key is required, it should be a **stable logical key**,
not one that includes the Temporal Activity attempt number:

```text
cts_job_id + transcript_or_chunk_id + enrichment_schema_version + model_policy_version
```

The Activity attempt number is useful as audit metadata, but it should
**not** form part of the uniqueness constraint — including it would make
each retry create a distinct durable result, defeating exactly-once
logical persistence across retries.

**Operating assumption for initial rollout**: the `enrich_optional`
activity performs no external writes. This must be verified, not assumed.
If this assumption is violated by future changes, the idempotency key
requirement becomes mandatory before those changes are merged.

### 2.6 Timeout budgets

A single informal constant is insufficient. Named time budgets are required.
The maximums of the sub-budgets below sum to 360 seconds
(30 + 120 + 180 + 30), which **exceeds** the 300-second nanny lease TTL.
Setting `start_to_close = 300s` "matching the TTL" is therefore not safe
without lease renewal: any scheduler delay, cancellation handling, final
HTTP round trip, or cleanup after the lease reaches its TTL can create an
avoidable race.

The pilot must choose one explicit initial policy:

| Option | Activity timeout | Readiness cap | Lease TTL | Renewal required? | Use when |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Short bounded degradation | 180–240s | 60–90s | 300s | No | Enrichment is optional and cold-start failure should fail fast |
| Full budget with renewal | 390–450s | 120s | 300s | Yes | Tolerate 120s cold start plus long inference |
| Increased nanny TTL | 390–450s | 120s | 480–600s | Preferably | Workloads routinely require longer inference |
| Split activity phases | Separate acquire/readiness and inference activities | 120s / per-phase | 300s | Depends | Clearer retry semantics and metrics |

**Recommended initial pilot policy**: short bounded degradation.

| Budget | Initial value | Notes |
| :--- | :--- | :--- |
| Intent + nanny admission | 15–30s | Includes queue/admission response |
| Ollama readiness | **60–90s** (capped) | Reduced from 120s to avoid consuming the full activity budget on cold start |
| Inference | Capped by model/context/output settings | Measure by model, context size, and token cap |
| Cleanup/telemetry | 15–30s | Must not consume all remaining activity time |
| `start_to_close_timeout` | **240s** initially | Conservative ceiling; adjust after observed percentile data |
| `schedule_to_close_timeout` | **10–15m** | Bounds all retry attempts across the activity |
| `heartbeat_timeout` | 90–120s (if used) | Configure before long-running rollout |

This preserves scale-to-zero while avoiding an initial pilot that can
consume the whole lease lifetime waiting for a cold start. If the readiness
cap of 60–90s proves too aggressive for real cold-start times, the correct
response is to implement lease renewal and raise the budget — not to set
the activity timeout equal to the TTL without renewal.

A `schedule_to_close_timeout` is required to bound total retry time —
without it, a 240s `start_to_close` combined with automatic retries can
create unexpectedly long workflow behavior.

These values must be set via the `CTS_TEMPORAL_TIMEOUTS` env override,
documented as a code-owner-approved tuning per Rec 7 of the pilot design.
Implement lease renewal before permitting larger prompts, longer output
limits, multiple LLM calls, or high-concurrency enrichment.

### Initial pilot policy

The initial pilot uses short-bounded optional enrichment:

- `start_to_close_timeout`: 240 seconds
- Ollama readiness budget: 60–90 seconds
- Inference must operate within the remaining Activity budget
- `schedule_to_close_timeout`: explicitly configured to bound all retries
- Lease renewal: not enabled for the initial pilot
- Eligibility: prompt size, model selection, output-token limit, and number
  of Ollama calls must be constrained so observed end-to-end enrichment
  remains safely below the 300-second lease TTL
- Long-running inference: out of scope until nanny lease renewal and
  Temporal Activity heartbeats are implemented and validated

### 2.7 Temporal heartbeats vs. nanny lease renewal

These are distinct mechanisms and must be designed separately:

- **Temporal Activity heartbeats** tell Temporal that the Activity worker
  is alive, enable prompt detection of worker loss, carry resumable
  progress, and allow cancellation delivery.
- **GPU Nanny lease renewal** keeps the GPU allocation valid and prevents
  the controller from treating the holder as abandoned.

For work that can run close to or beyond the 300-second lease TTL, both
must be implemented:
- A Temporal `heartbeat_timeout`, with heartbeats at a conservative
  interval (30–60s). The heartbeat timeout should be several times the
  expected heartbeat interval.
- A GPU Nanny lease renewal at an interval below the TTL (60–90s for a
  300s TTL).
- Explicit behavior if renewal fails: stop issuing new work, attempt final
  cleanup, and return/degrade according to the retry policy.

**Operating assumption for initial rollout**: the maximum supported
enrichment invocation, including model loading and response processing, is
demonstrably below the 300-second nanny lease TTL with sufficient margin.
If this assumption holds, heartbeat/renewal can be a follow-up. If it does
not hold, both mechanisms must be implemented before the first canary.

### 2.8 Incremental enablement

The pilot remains opt-in. Enabling it does not require migrating all jobs:

1. Set `CTS_TEMPORAL_PILOT_ENABLED=true`.
2. Jobs tagged with `source_system = "cts_temporal_pilot"` route to Temporal.
3. All other jobs continue on the existing DB-queue + subprocess pipeline
   unchanged.

This allows a gradual rollout: pilot jobs validate the wiring end-to-end
before broader adoption.

---

## 3. Rollout Sequence

The rollout is structured as two hard gates followed by a deployment
sequence and expansion criteria. No infrastructure change, pilot flag
change, or production-like test may proceed until both gates are satisfied.

### Gate 0 — Preserve the pilot implementation (source-control recovery)

Before any manifest change, pilot flag change, or production-like test:

1. Create a dedicated branch from the desired integration base
   (`feature/cts-temporal-pilot`, separate from
   `security/comprehensive-secret-remediation` — the two changes differ in
   risk domain, ownership, test surface, rollout plan, and rollback
   criteria).
2. Commit the full Temporal pilot, API routing integration, migration,
   tests, and canary script:
   - `src/temporal_pilot/` (all 9 files)
   - `src/ingestion/api_server.py` (the +152 line routing integration)
   - `scripts/launch_temporal_pilot_canary.sh`
   - `src/database/migrations/versions/c3d4e5f6a7b8_add_temporal_submission_dlq.py`
   - `tests/test_completeness.py`
   - `tests/test_terminal_record.py`
3. Push the branch to the remote.
4. Open a focused PR and run the test/build pipeline.
5. Confirm the container image used by `cts-backend` contains the committed
   `src.temporal_pilot` package.
6. Commit ADR-035 and the dependency audit separately in `AI_AGENTS`.

### Gate 1 — Reliability (timeout, retry, cleanup, idempotency)

Before the first canary:

1. Implement the timeout budget (§2.6) with named values and the chosen
   initial policy.
2. Implement the error taxonomy (§2.4) with bounded retry semantics.
3. Implement exception-safe `finally` cleanup (§2.1) with ticket-based
   lease release.
4. Verify the `enrich_optional` activity's side-effect profile (§2.5) by
   tracing all calls below `analyze_chunk_with_ollama`. Define an
   idempotency key if any external write is found.
5. Verify the combined timeout plan cannot exceed the nanny lease TTL
   without renewals, or implement renewals if it can.

### Deployment sequence (after both gates pass)

| Step | Action | Owner |
| :--- | :--- | :--- |
| 1 | **Implement shared client factory.** Extract `make_ollama_client()` into a shared module. (Gate 1 prerequisite) | CTS code owner |
| 2 | **Implement lease-aware enrichment.** Add lease acquire, readiness wait, inference, release-in-`finally`, structured failure classification, and bounded retry behavior. (Gate 1) | CTS code owner |
| 3 | **Add environment and security configuration.** Add `GPU_NANNY_HOST`, `GPU_NANNY_PORT`, `OLLAMA_HOST` to the sidecar. Verify NetworkPolicy/DNS/service auth, Kubernetes RBAC (if needed), and nanny controller RBAC per §2.3. | CTS code owner + operator |
| 4 | **Set timeout and retry policy explicitly.** Set `start_to_close`, `schedule_to_close`, retry limits/backoff, and, if applicable, heartbeat timeout. Ensure the combined timeout plan respects the nanny lease TTL per §2.6. | CTS code owner |
| 5 | **Deploy with the pilot flag still disabled.** Validate sidecar readiness, import success, Temporal worker registration, nanny connectivity, and metrics before exposing routing. | Operator |
| 6 | **Run pre-canary smoke tests inside the sidecar container.** Verify the actual call chain from the exact sidecar image (see §4.5). | Operator |
| 7 | **Run an intentional scale-from-zero canary.** Scale Ollama to zero through the expected controller path, submit exactly one pilot-tagged job, and verify the complete lifecycle. | Operator |
| 8 | **Exercise failure cases deliberately.** Test nanny unavailable, Ollama readiness timeout, inference error, activity retry, worker restart while holding a lease, cancellation, and duplicate submission. | Operator |
| 9 | **Enable narrowly and observe.** Set `CTS_TEMPORAL_PILOT_ENABLED=true` only after the canary criteria pass. | Operator |

### Rollout preconditions (added after Gate 1.7 canary investigation)

Before enabling CTS Temporal pilot traffic, the following infrastructure
preconditions must be satisfied:

1. **Pin the Ollama image.** Replace `ollama/ollama:latest` with an
   immutable reference (version tag + digest). The current pinned version
   is `ollama/ollama:0.33.3@sha256:32931b46719f673c05fdbaa81ccb26da18ea4a1c57590a754874ab28ba269eb2`.
   This makes the node image cache trustworthy and ensures rollback/reproducibility.

2. **Pre-cache the image on all eligible nodes.** A DaemonSet
   (`ollama-image-prepull` in `shared-infra`) ensures the pinned image is
   present on every node matching the Ollama Deployment's nodeSelector.
   Verify after node rebuild, node replacement, image-tag change, or
   model/version change:
   ```
   kubectl get ds -n shared-infra ollama-image-prepull
   kubectl get pods -n shared-infra -l app=ollama-image-prepull -o wide
   ```

3. **Strict lease admission.** The OllamaClient must distinguish "Ollama
   HTTP ready" from "GPU lease ACTIVE" and begin inference only after both
   conditions are true. This preserves the nanny's slot arbitration
   guarantee. A lease that remains QUEUED past the readiness budget is
   treated as a timeout, not a silent bypass.

4. **Success-path canary.** At least one canary demonstrating: intent →
   nanny scale-up → Ollama ready → lease ACTIVE → successful enrichment →
   ticket release → idle scale-down.

### Canary status (2026-09-04)

**Degradation-path canary #1 (`job_20260904125749_0_q`): PASSED.** One job
completed the full non-enrichment lifecycle. The nanny registered the
Ollama intent and successfully scaled the Deployment from 0 to 1. The
enrichment canary timed out because the first pull of the uncached 3.7 GB
Ollama image took ~120 seconds, exceeding the 90-second readiness budget.
The lease was released cleanly and the workflow completed with
`status=success, stage=enrichment, cause=completed, chunks=1/1`.

**Degradation-path canary #2 (`job_20260904204251_0_q`): PASSED.** Image
was cached (pre-pull DaemonSet active), transcription succeeded. Lease
`lease_aee7f56c` created but stayed QUEUED — all 4 GPU slots occupied by
Whisper. Strict admission correctly refused inference without ACTIVE
lease. Timed out with precise diagnostics:
`lease not admitted (state=QUEUED) within 90s`. Lease released cleanly,
workflow COMPLETED with `status=success, chunks=1/1`.

**Success-path canary (`job_20260904220838_0_q`): PASSED.** With free GPU
slots and the `llama3:8b` model pre-loaded, the full enrichment lifecycle
completed:

1. CTS pilot submission (`source_type=cts_temporal_pilot`)
2. Ollama intent registered → nanny scaled Ollama 0→1
3. Audio downloaded and chunked
4. Whisper transcription: 20 segments, 850 chars, 160.3s
5. Lease acquired: `state=ADMITTED ticket=lease_653e8da0`
6. Strict admission passed: lease ADMITTED on first poll
7. Ollama inference: `POST /api/chat "HTTP/1.1 200 OK"`
8. Enrichment result returned
9. Lease released: `status=complete`
10. Terminal record written: `status=success, stage=enrichment, cause=completed, chunks=1/1`
11. Workflow COMPLETED

All ten lifecycle steps completed successfully. The success-path canary
was run with `GPU_SLOTS=4` (original capacity), free GPU slots available,
image pre-cached, and the `llama3:8b` model pre-loaded in Ollama.

### Expansion criteria

Broaden the source-system routing criterion in separately reviewed
increments, gated on:
- Performance: observed p99 enrichment latency within budget.
- Error rate: degradation rate below an agreed threshold.
- Lease leak rate: zero unreconciled leaked leases over a sustained period.
- Operator sign-off: explicit approval for each routing expansion.

---

## 4. Acceptance Criteria

### 4.1 Source-control gates

- [x] The complete pilot package, routing changes, migration, tests, and
      canary script are committed, pushed, and included in a reviewed PR.
- [x] The deployed sidecar image is built from a revision containing
      `src.temporal_pilot`.
- [x] ADR-035 is committed in its governance repository.
- [x] The pilot code has a documented rollback commit or image tag.

### 4.2 Functional canary

- [x] A pilot-tagged job creates one Temporal workflow with the expected
      workflow ID.
- [ ] A repeated start with the same job ID is rejected or attached to an
      existing workflow according to an explicitly documented API behavior.
- [x] With Ollama at zero replicas, the nanny receives an intent and scales
      the Deployment from 0 to 1.
- [x] The activity does not call Ollama before readiness succeeds.
- [x] The activity receives an ACTIVE lease before inference (strict admission).
- [x] On normal completion, enrichment output is persisted once and the
      lease is released.
- [ ] With no active leases, the nanny returns Ollama to zero according to
      its configured idle policy.

### 4.3 Failure and recovery

- [ ] Nanny unreachable produces a classified degraded enrichment result
      and an observable metric/event.
- [x] Ollama cold-start timeout produces a classified degraded enrichment
      result without failing the transcript workflow.
- [ ] A worker restart during an active lease does not result in permanent
      GPU allocation; the TTL/reconciliation path recovers it.
- [x] An Activity retry does not produce duplicate enrichment records,
      duplicate downstream writes, or leaked leases.
- [ ] Cancellation releases or expires the lease promptly and does not
      report enrichment as complete.

### 4.4 Observability

At minimum, emit and dashboard:

- `ollama_lease_request_total` by outcome
- `ollama_lease_acquire_duration_seconds`
- `ollama_ready_wait_duration_seconds`
- `ollama_enrichment_duration_seconds`
- `ollama_lease_release_total` by outcome
- `cts_enrichment_degraded_total` by reason
- Temporal Activity attempt count and timeout count
- Deployment desired/available replicas and time spent scaled above zero

Correlation fields on all events: `job_id`, Temporal workflow ID/run ID,
activity ID/attempt, lease ID, model name, and chunk ID (if applicable).

**Do not log** prompt bodies, transcript content, or credentials in these
events.

### 4.5 Pre-canary smoke test (inside the sidecar container)

Before the first canary job, run a smoke test **inside the
`cts-temporal-worker` container** that verifies the actual call chain from
the exact sidecar image:

```bash
# DNS resolution
getent hosts gpu-nanny-controller.toneroot.svc.cluster.local
getent hosts ollama.shared-infra.svc.cluster.local

# TCP connectivity
python3 -c "import socket; socket.create_connection(('gpu-nanny-controller.toneroot.svc.cluster.local', 8081), timeout=5)"
python3 -c "import socket; socket.create_connection(('ollama.shared-infra.svc.cluster.local', 1434), timeout=5)"

# Nanny health/readiness (if endpoint available)
curl -s -o /dev/null -w '%{http_code}' http://gpu-nanny-controller.toneroot.svc.cluster.local:8081/capacity

# Ollama /api/tags behavior while service is at zero replicas
# (expected: connection refused — confirms the gap this ADR addresses)
curl -s --max-time 3 http://ollama.shared-infra.svc.cluster.local:1434/api/tags || true

# Sidecar import and startup
python3 -c "import src.temporal_pilot.worker"
python3 -c "import src.temporal_pilot.dlq_replay"

# Image revision matches the reviewed CTS pilot commit
python3 -c "import src.temporal_pilot; print(getattr(src.temporal_pilot, '__version__', 'unknown'))"
```

- [ ] DNS resolves for both nanny and Ollama from inside the sidecar.
- [ ] TCP connectivity to nanny port 8081 succeeds.
- [ ] TCP connectivity to Ollama port 1434 succeeds when Ollama is scaled
      up (and fails when at zero — confirming the gap).
- [ ] Nanny health/readiness endpoint responds.
- [ ] `import src.temporal_pilot.worker` succeeds in the sidecar image.
- [ ] `import src.temporal_pilot.dlq_replay` succeeds in the sidecar image.
- [ ] The image revision/SHA matches the reviewed CTS pilot commit.

---

## 5. Architecture Refinements

### 5.1 Use a lease ID, not only `job_id`, for cleanup

A job may have multiple chunks or retries. The client should return a
distinct lease handle/ID, with `job_id` retained as correlation metadata.
Releasing "the lease for job ID" is potentially ambiguous under retries or
future parallelization. The `OllamaClient` already tracks
`self.leases[job_id] = {"ticket_id": ...}` — the `ticket_id` is the lease
handle and should be used for release, not the `job_id` alone.

### 5.2 Define exclusivity precisely

"Exclusive access" should be verified against the nanny's actual admission
model. If `vram_mb: 4000` and two GPUs are free, does the nanny allow more
than one Ollama lease? Does Ollama itself serialize requests? Does a lease
reserve a GPU, a service replica, or a VRAM budget? The ADR wording must
match real behavior. The nanny's `GPU_SLOTS` (default 4) and
`_count_active_leases()` suggest slot-based admission, not per-GPU
reservation — this should be confirmed and documented.

### 5.3 Avoid holding a lease for non-GPU work

Acquire the lease immediately before the first Ollama request and release
it immediately after the final one. Do not hold it through transcript
download, chunk preparation, persistence, or optional post-processing. The
current activity structure (enrichment is a single stage after merge) is
already minimal in this regard.

### 5.4 Scope of `analyze_chunk` within the activity

If the activity analyzes several chunks sequentially, decide whether it
takes one activity-wide lease or a lease per chunk. One activity-wide lease
reduces cold starts but can monopolize capacity; per-chunk leases improve
fairness but can cause scale churn. The current `enrich_optional` activity
processes the merged transcript as a single input (`input.transcript[:5000]`),
so a single activity-wide lease is appropriate. If this changes to per-chunk
enrichment, the lease scope decision must be revisited.

### 5.5 Manual override semantics

Since Flux reconciliation is disabled and scaling has been manual, the ADR
must specify:
- Whether manual scale-to-zero is permitted while leases are active.
- Whether the nanny owns the replica count exclusively, or manual `kubectl
  scale` is an accepted break-glass operation.
- What break-glass restoration looks like under ADR-028 (Service Delivery
  and Break-Glass Recovery Framework).

**Operating assumption**: the nanny owns the replica count during pilot
operation. Manual `kubectl scale` is a break-glass action that must be
documented as an ADR-028 emergency deployment, and the nanny's
reconciliation must be allowed to restore the desired state afterward.

---

## 6. Consequences

### Positive

- **On-demand scale-up from Temporal**: pilot jobs trigger Ollama scale-up
  via the existing nanny lease system, eliminating the "Ollama is always
  down" failure mode for Temporal-routed jobs.
- **Consistency with ADR-020**: both the Temporal and non-Temporal job
  paths use the same lease-based GPU arbitration, preventing VRAM
  contention.
- **At-most-one workflow execution**: `REJECT_DUPLICATE` with
  `workflow_id = job_id` enforces at most one workflow execution per CTS
  job ID within the Namespace retention window.
- **Scale-to-zero maintained**: Ollama returns to 0 replicas when no leases
  are active, preserving GPU capacity for other workloads.
- **Graceful degradation unchanged**: if Ollama cannot scale up within the
  timeout, the workflow still succeeds if transcription completed.
- **Retry-safe cleanup**: the `finally` path ensures lease release across
  all exit conditions, and nanny TTL reconciles leaked leases from worker
  crashes.

### Negative

- **Cold-start latency in the Temporal path**: the first pilot job after
  Ollama has been at zero replicas incurs up to 120s of readiness polling
  before enrichment can run. This is inherent to scale-to-zero and already
  accepted by the non-Temporal path.
- **`REJECT_DUPLICATE` prevents re-drive under same job ID**: a failed
  pilot job cannot be replayed under the same `job_id`. Operational re-drive
  requires a new job ID, a Temporal reset/retry mechanism, or a
  domain-level attempt/version identifier. This must be documented in the
  pilot runbook.
- **Nanny dependency in the sidecar**: the Temporal worker sidecar now
  depends on the GPU Nanny being reachable. If the nanny is down, lease
  acquisition fails and enrichment degrades — acceptable, but must be
  monitored.
- **Timeout budget complexity**: named time budgets and
  `schedule_to_close_timeout` add configuration surface area. Values must
  be tuned from observed percentile data, not set once and forgotten.

---

## 7. Pilot Re-Drive Rule

> **Pilot re-drive rule:** A failed or corrected CTS job must receive a new
> domain job ID before submitting a fresh Temporal Workflow Execution.
> Temporal reset is not part of pilot operations unless a documented reset
> procedure proves that all external activity side effects remain safe.

This removes ambiguity from DLQ replay and operator behavior. If the DLQ
replayer simply attempts the old job ID again, it will deterministically
fail due to `REJECT_DUPLICATE`, depending on workflow state and the
client/start semantics. The DLQ replayer must either:
- Generate a new job ID for each re-drive attempt, or
- Skip jobs whose workflow executions are still within the Namespace
  retention window and surface them for manual review.

This rule must be documented in the pilot runbook and verified in the DLQ
replay acceptance criteria.

## 8. Open Questions

1. **~~Re-drive under `REJECT_DUPLICATE`~~** — **Resolved.** See §7 (Pilot
   Re-Drive Rule): failed or corrected jobs must receive a new domain job
   ID. A domain-level attempt/version identifier (e.g., `job_id#attempt_2`)
   remains a future option if re-drive volume makes new-ID generation
   cumbersome, but it is not required for the initial pilot.

2. **Nanny exclusivity model**: does the nanny allow concurrent Ollama
   leases when multiple GPU slots are free, or does Ollama's single-process
   model serialize requests regardless? This affects whether parallel
   pilot jobs can share a scaled-up Ollama pod.

3. **Lease renewal during long inference**: if enrichment inference
   approaches the 300s TTL, should the activity heartbeat both Temporal
   and the nanny? Recommendation: implement if observed inference
   percentiles exceed 240s (80% of TTL).

4. **Should the non-enrichment activities (transcribe_chunk) also acquire
   leases?** `transcribe_chunk` calls the shared Whisper service, which is
   itself a GPU workload governed by the nanny. Currently it calls Whisper
   directly. This is out of scope for this ADR but noted as a follow-up.

---

## 9. Implementation Status

| Component | Status | Location |
| :--- | :--- | :--- |
| CTS Temporal workflow + activities | Implemented (uncommitted) | `cts/src/temporal_pilot/workflow.py` |
| CTS Temporal worker sidecar | Manifest in PR #1; code uncommitted | `cts-backend` pod, `cts-temporal-worker` container |
| Workflow ID reuse (`REJECT_DUPLICATE`) | Implemented (uncommitted) | `cts/src/temporal_pilot/routing.py` |
| API server Temporal routing (+152 lines) | Implemented (uncommitted) | `cts/src/ingestion/api_server.py` |
| GPU Nanny lease system | Committed and deployed | `apps/gpu-nanny-controller/base/gpu_nanny_controller.py` |
| `OllamaClient` lease lifecycle | Committed (non-Temporal path) | `cts/src/ingestion/api_server.py` |
| `make_ollama_client()` shared factory | **Not started** (this ADR) | New shared module |
| `enrich_optional` lease wiring + `finally` cleanup | **Not started** (this ADR) | `cts/src/temporal_pilot/workflow.py` |
| Error taxonomy + bounded retry | **Not started** (this ADR) | `cts/src/temporal_pilot/workflow.py` |
| Timeout budget (`start_to_close`, `schedule_to_close`) | **Not started** (this ADR) | `CTS_TEMPORAL_TIMEOUTS` env override |
| Sidecar env vars (`GPU_NANNY_*`, `OLLAMA_HOST`) | **Not started** (this ADR) | `cts-backend` Deployment spec |
| Sidecar network access (RBAC, NetworkPolicy) | **Not verified** (this ADR) | Cluster policy |
| Pilot enablement (`CTS_TEMPORAL_PILOT_ENABLED=true`) | **Not started** | `cts-backend` Deployment env |
| ADR-035 committed | **Not started** | `AI_AGENTS` repo |
| ADR-035 dependency audit | Written (uncommitted) | `AI_AGENTS/global/adr/ADR-035-dependency-git-status.md` |

---

## 10. Summary

The CTS Temporal pilot, the GPU Nanny scale-up lease system, and the
workflow-level `REJECT_DUPLICATE` acceptance policy all exist. The missing
wiring is narrow in concept but requires careful operational correctness:
the `enrich_optional` activity must acquire and release leases in a
retry-safe `finally` path using ticket-based handles, use an explicit error
taxonomy with bounded retries, and operate within named timeout budgets
that respect the nanny lease TTL. The pilot code is currently uncommitted
and must be preserved in source control before any deployment or
enablement work begins. The architecture is sound — reuse the nanny rather
than introducing another scaler, preserve scale-to-zero, keep the pilot
opt-in — but the main risks are operational correctness under retries,
long-running work, and the immediate danger of losing the uncommitted
pilot implementation.

The remaining architectural decision is whether the pilot is intentionally
short-bounded and degradation-oriented (the recommended initial policy:
240s activity timeout, 60–90s readiness cap, no renewal), or whether it
must support long-running inference — in which case lease renewal and a
TTL/timeout redesign are prerequisites rather than follow-up work.

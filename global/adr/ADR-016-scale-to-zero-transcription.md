# ADR-016: Scale-to-Zero Transcription via Shared Capability Queues

**Status:** Accepted  
**Date:** 2026-06-07  
**Author:** Cascade (AI Assistant)  
**Context:** ToneRoot Nexus transcription architecture for GPU Whisper workers

---

## Summary

Design the transcription subsystem to scale GPU workers from zero while maintaining responsiveness for user-triggered requests. The solution prioritizes late-binding queue resolution, graceful drain handling, and worker self-selection over pre-provisioned capacity.

---

## Problem Statement

The transcription subsystem faces three competing constraints:

1. **Cost sensitivity:** GPU resources are expensive; idle workers should not consume capacity
2. **User experience:** Explicit transcription requests (e.g., "get lyrics for this track") should not wait minutes for cold-start
3. **Correctness:** Jobs must not be lost when workers scale down, and duplicate transcription must be prevented

The existing architecture used a single shared queue (`gpu_queue:whisper`) with always-on workers. This wasted GPU time during idle periods and could not scale to rented/external GPU capacity.

---

## Decision

**Queue names encode capability requirements, not worker identity.**

Specifically:

| Queue | Capability Required |
|-------|---------------------|
| `queue:whisper:gpu:urgent` | GPU, urgent priority |
| `queue:whisper:gpu:batch` | GPU, normal priority |
| `queue:whisper:cpu:normal` | CPU only (fallback) |
| `queue:whisper:pending` | None (parked when no capacity) |

Workers self-select which queues to serve based on startup capability detection (GPU probe via `torch.cuda`). The dispatcher routes to capabilities, not to specific workers.

The WorkerRegistry is **observability-only** — the system functions correctly even with stale registry data, using the PENDING queue as a universal fallback.

---

## Consequences

### Positive

- **Scale-to-zero enabled:** Workers can scale from zero because queue names don't contain worker identity
- **Graceful degradation:** When GPU unavailable, jobs park in PENDING and get claimed when workers start
- **Drain safety:** In-flight tasks complete before worker termination (state machine: `ACTIVE → DRAINING → DRAINED`)
- **Duplicate prevention:** Distributed locks with TTL renewal prevent concurrent transcription of same UUID
- **Multiple GPU tiers:** Separate queues for `large-v3` (≥10GB) vs `base` models enable heterogeneous workers

### Negative

- **Increased complexity:** State machine for drain handling, lock renewal threads, heartbeat management
- **KEDA signal drift:** Workers must decrement signal counters; drift requires periodic reconciliation
- **Longer graceful periods:** `terminationGracePeriodSeconds: 1800` required for 2-hour audio files

---

## Alternatives Considered

### Alternative 1: Per-Worker Named Queues

**Approach:** `gpu_queue:whisper:worker-01`, `gpu_queue:whisper:worker-02`

**Rejected:** Dispatcher must know worker ID before worker exists. Breaks scale-to-zero — cannot route to a queue that doesn't exist yet.

### Alternative 2: Push-Based Routing

**Approach:** API pushes jobs directly to workers via WebSocket or direct connection

**Rejected:** Same problem — requires live worker to receive push. Cannot scale from zero. Also couples dispatcher to worker lifecycle.

### Alternative 3: Always-On Minimal Capacity

**Approach:** Keep 1 GPU worker always running, scale additional for burst

**Rejected:** Violates cost constraint. 1 GPU always-on is acceptable for production, but this is a homelab system with cost sensitivity. Also doesn't generalize to rented GPU models.

### Alternative 4: Static Queue Assignment

**Approach:** Pre-assign jobs to specific queues based on job properties

**Rejected:** Requires perfect prediction of which workers will be alive when job executes. Brittle with dynamic scaling.

---

## Implementation Details

### Queue Architecture

```python
class QueueNames:
    # Shared by capability — no worker identity in the name
    GPU_URGENT = "queue:whisper:gpu:urgent"
    GPU_BATCH = "queue:whisper:gpu:batch"
    CPU_FALLBACK = "queue:whisper:cpu:normal"
    PENDING = "queue:whisper:pending"
    
    # KEDA signal queues (mirrors for scaling decisions)
    KEDA_GPU_URGENT = "keda:signal:gpu:urgent"
    KEDA_GPU_BATCH = "keda:signal:gpu:batch"
```

### Worker Startup Sequence

```python
def main():
    capabilities = detect_capabilities()  # torch.cuda probe
    WorkerRegistry.register(WORKER_ID, capabilities)
    claim_pending_work(max_claim=20)    # Scale-from-zero recovery
    heartbeat_thread.start()
    worker_poll_loop()
```

### Drain State Machine

```
ACTIVE ──(SIGTERM / operator drain)──► DRAINING ──(in-flight==0)──► DRAINED
   │                                      │
   │                                      └── Refuse new work, wait for completion
   │
   └── Accept work from capability queues
```

### Lock Pattern for Idempotency

```python
class TranscriptionLock:
    def __init__(self, uuid, lock_timeout=600, renew_interval=300):
        # 600s timeout, renew at 300s to prevent expiration mid-job
        self.lock_key = f"transcribe:lock:{uuid}"
    
    def acquire(self):
        # Redis SET NX EX — atomic acquire
        if acquired:
            threading.Thread(target=self._renew_loop, daemon=True).start()
    
    def _renew_loop(self):
        while not stopped:
            time.sleep(self.renew_interval)
            r_client.expire(self.lock_key, self.lock_timeout)
```

---

## Performance Characteristics

| Metric | Target | Achieved |
|--------|--------|----------|
| Scale-up latency (0→1) | < 30s | ~10s (5s poll + activation delay) |
| Drain latency | < max(job_runtime, 1s) | Bounded by poll loop |
| Duplicate prevention | 100% | Lock + DB double-check |
| Stale registry tolerance | graceful | PENDING queue fallback |

---

## Operational Validation

```bash
# Verify KEDA is watching correct keys
kubectl describe scaledobject toneroot-whisper-gpu -n toneroot
# Look for: listName: keda:signal:gpu:urgent

# Smoke test scaling
redis-cli -h redis.toneroot.svc.cluster.local LPUSH keda:signal:gpu:urgent "1"
kubectl get hpa -n toneroot -w  # Should scale 0 -> 1 within ~10s

# Verify graceful drain
kubectl exec -n toneroot deployment/toneroot-whisper-gpu -- /bin/sh -c \
  "redis-cli -h redis.toneroot.svc.cluster.local HSET worker:\$HOSTNAME drain_state draining"
# Pod should finish in-flight, then exit cleanly
```

---

## Related Documents

- `application/apps/toneroot/web/backend/api.py` — API layer with QueueNames, TranscriptionLock, WorkerRegistry
- `application/apps/toneroot/web/backend/whisper_worker.py` — Worker implementation
- `infrastructure/apps/toneroot/whisper-scaledobject.yaml` — KEDA ScaledObjects and Deployments

---

## Future Work (Out of Scope)

- **GPU-Nanny lease manager:** Provision rented GPU (Vast.ai, Lambda, RunPod) when pending backlog exceeds threshold
- **CPU fallback activation:** Currently stubbed — implement CPU-only Whisper for when no GPU available
- **Per-user rate limiting:** Prevent queue starvation from single user flooding

---

## Decision Record

This decision was reached through iterative refinement with human feedback on:
1. Correct Celery patterns (countdown vs time.sleep)
2. Distributed lock design (renewal pattern vs fixed TTL)
3. KEDA configuration (exact keys vs wildcards)
4. Grace period requirements (terminationGracePeriodSeconds > job runtime)

The architecture is now frozen for implementation. Changes require ADR amendment.

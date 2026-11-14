# ADR-018: KEDA/Flux/Tilt Authority Arbitration Protocol

## Status
Accepted

## Context
This workspace employs a unified cluster for both production and development, managed by a combination of controllers with competing views of the desired system state:
- **Flux (GitOps):** Enforces the declarative state from Git (e.g., `minReplicaCount: 0` to satisfy the "Rule of Fiscal Gravity").
- **KEDA (Auto-scaling):** Dynamically scales deployments based on workload metrics.
- **Tilt (Local Dev):** Artificially pins deployments (e.g., `minReplicaCount: 1`) to ensure services are warm and responsive for iterative development.

A structural race condition ("Controller Conflict") occurs when Tilt overrides `minReplicaCount` via a direct patch. Flux detects this drift from the Git baseline and reverts it. KEDA sequentially obeys both controllers, resulting in rapid creation and termination of Pods (thrashing). This not only disrupts development but also causes `FailedScheduling` errors as terminating pods retain resource reservations.

Historically, this was mitigated via a manual `flux suspend kustomization apps` step, which introduced a fragile human-in-the-loop and a wide blast radius (suspending all apps).

## Decision
We establish an **Annotation-Based Arbitration Model** using KEDA's native pause functionality, rendering controller arbitration safe, atomic, and zero-blast-radius. 

1. **No controller may patch `ScaledObject.spec` while Flux is active.**
   - All dev-mode scaling overrides MUST use the `autoscaling.keda.sh/paused-replicas` annotation. This takes precedence over `minReplicaCount` within KEDA, allowing Flux to continuously reconcile the baseline Git state (`minReplicas: 0`) without triggering a thrash.
   
2. **Dev-mode teardown is always atomic.**
   - The removal of the pause annotation must be automated in the `Tiltfile`'s teardown sequence (`tilt down`). It must never rely on manual operator commands.

3. **CI/CD Temporal Dependency and Resumption.**
   - `f5-tts-service` and other heavy workloads have a ~15-20 min build time. By eliminating the need to suspend Flux during dev sessions, `ImageUpdateAutomation` can seamlessly apply new image tags immediately after the build workflow finishes without requiring a manual `flux resume` step. The updated images will be pulled gracefully the next time the replica count > 0.

## Consequences
- **Positive:** Controller thrashing is eliminated at the architectural level. Dev-mode activation no longer suspends Git updates for unaffected services (zero blast radius).
- **Positive:** Eliminates the human-in-the-loop for managing Flux state during active development.
- **Negative/Constraint:** Requires KEDA v2.4+ (validated as available). All developers must ensure their `Tiltfile` uses `kubectl annotate` rather than `kubectl patch` for `ScaledObject` pinning.

## Implementation Examples

### ToneRoot (2026-06-08)
Applied the arbitration protocol to resolve the "image tag revert" conflict where Flux would immediately revert Tilt's dev image deployments.

**Tiltfile Changes:**
- Added `SCALEDOBJECTS` list with `toneroot-whisper-gpu`
- `dev-mode: active` resource with KEDA paused-replicas annotation
- `make_watchdog` function for Flux reconciliation disable
- Watchdogs applied to `toneroot-backend`, `toneroot-worker`, `toneroot-frontend`
- Dev mode teardown on `tilt down` to clean up annotations

**Infrastructure Changes:**
- Added explicit `command` and `args` to `toneroot-backend` deployment to establish Tilt Command Ownership
- The worker and frontend already had explicit commands (celery and npm respectively)

This ensures that when `sov-up` is run from the `application/apps/toneroot` directory, Tilt gains exclusive authority over its target deployments and automatically hands them back to Flux on teardown with complete state coherency.

### Flux→Tilt Image Race Fix (2026-07-01)
Discovered a race condition where Flux could reconcile the infrastructure `deployment.yaml` (with production image tags) between Tilt's `k8s_yaml()` call and the async `local_resource` that suspends Flux. This caused the `toneroot-backend` container to revert to a stale production image while the `toneroot-ipc` sidecar kept the Tilt dev image — creating a mixed-image ReplicaSet split.

**Root cause:** `k8s_yaml()` runs synchronously during Tiltfile loading, but Flux suspension was deferred to an async `local_resource`. A ~2-5s window allowed Flux to overwrite Tilt's images.

**Layered fix applied:**

1. **Synchronous pre-suspend (`local()`):** Added a blocking `local()` call *before* `k8s_yaml()` that suspends Flux kustomizations during Tiltfile loading. Eliminates the race window entirely.

2. **Object-level annotation:** Added `kustomize.toolkit.fluxcd.io/reconcile: disabled` to all three Deployments in `deploy.yaml` (backend, worker, frontend). This tells Flux to skip these objects even if the kustomization runs.

3. **RollingUpdate strategy:** Added `maxUnavailable: 0`, `maxSurge: 1`, `minReadySeconds: 5` to the backend Deployment. Prevents the mixed-image RS split by ensuring the old RS only scales down after the new pod passes readiness.

4. **Watchdog retained:** The existing `flux: suspend toneroot-app` local_resource now acts purely as a re-suspension watchdog (every 300s) and teardown handler (resume on `tilt down`).

### Structural Fix: Flux Base + Tilt Patch Overlay (2026-07-01)
Eliminated dual ownership by moving from "two full Deployment YAMLs" to "Flux owns base, Tilt applies kustomize overlay."

**Layout:**
```
infrastructure/apps/toneroot/
  app/                                    ← Flux-managed base (production)
    deployment.yaml
    kustomization.yaml

application/apps/toneroot/
  kustomize-dev/                          ← Tilt-only overlay (outside Flux tree)
    kustomization.yaml                    (references ../../../../infrastructure/.../app)
    backend-dev-patch.yaml
    worker-dev-patch.yaml
    frontend-dev-patch.yaml
    ingress.yaml
    README.md
```

**Tiltfile change:**
```python
# Before (dual ownership):
k8s_yaml('deploy.yaml')

# After (single source of truth):
k8s_yaml(kustomize('kustomize-dev'))
```

**Key design choices:**
- `labels` with `includeSelectors: false` adds `tilt.dev/managed: "true"` without breaking pod selectors.
- `commonAnnotations` stamps `kustomize.toolkit.fluxcd.io/reconcile: disabled` on all emitted objects.
- Each container uses a distinct `-dev` image name matching its `docker_build` target (backend-dev, ipc-dev, worker-dev, frontend-dev).
- The `dev/` directory is never referenced by any Flux Kustomization — only Tilt consumes it.
- The old `application/apps/toneroot/deploy.yaml` is retained as a fallback reference but is no longer applied by the Tiltfile.

**Consequence:** Field drift between dev and prod is now visible as a diff between `dev/*.yaml` patches and the base `app/deployment.yaml`. No more "last writer wins" on the same Kubernetes object.

**Structural guarantee:** The dev overlay lives in `application/apps/toneroot/kustomize-dev/` — outside the `infrastructure/` tree that Flux watches. There is no path by which Flux can discover or apply the overlay, even by accident.

## Rules (binding for all ToneRoot Deployment changes)

1. **Single definition:** `infrastructure/apps/toneroot/app/deployment.yaml` is the sole definition of ToneRoot Deployments. Dev and test environments MUST apply changes via Kustomize patches, never by redefining the Deployment.
2. **Prod-and-dev changes** go in the base (`infrastructure/apps/toneroot/app/`).
3. **Dev-only changes** go as patch files in `application/apps/toneroot/kustomize-dev/`.
4. **Never place dev overlays inside `infrastructure/`** — Flux watches that tree.
5. **Image names must match `docker_build` targets** — each container uses a distinct `-dev` image name so Tilt can inject without ambiguity.

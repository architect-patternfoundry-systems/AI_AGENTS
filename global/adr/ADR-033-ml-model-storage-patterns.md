# ADR-033: ML Model Storage and Prestage Patterns

## Status

Proposed

## Context

The Sovereign Cluster hosts multiple GPU-accelerated ML workloads (TTS,
audio synthesis, image generation, transcription) that require large
model weights (1-15 GB per model). These weights are too large to bake
into container images and too expensive to download on every pod start.

As of 2026-08-31, four distinct patterns have emerged across the
workload fleet, with inconsistent adoption. This ADR codifies the
approved patterns and provides selection criteria.

### Current state audit

| Workload | Storage | Seeding | Image-warmer | Offline | PVC populated? |
|---|---|---|---|---|---|
| fish-speech | Static local PV (20Gi) | Prestage Job | No | Yes (`HF_HUB_OFFLINE=1`) | Yes (`.ready.json` present) |
| f5-tts | Static local PV (20Gi) | None (manual) | Yes | Yes (`HF_HUB_OFFLINE=1`) | No (empty) |
| ace-step-service | Static local PV (30Gi) | None (runtime download) | No | No | No (empty) |
| alltalk-tts | hostPath | None (manual) | Yes | No | Unknown (host dir) |
| stable-diffusion | local-path PVC (100Gi) | None (manual) | Yes | No | Unknown |
| whisper | NFS PVC (shared hf-cache) | None (runtime download) | No | No | Yes (shared cache) |
| storyloom | NFS PVC (shared hf-cache) | None (runtime download) | No | No | Yes (shared cache) |
| heartmula | Static local PV | None (runtime download) | No | No | Unknown |

### Problems with current state

1. **f5-tts has `HF_HUB_OFFLINE=1` but an empty PVC** — the workload
   cannot start successfully without manual intervention.
2. **ace-step has a PVC but no prestage Job** — the neural pipeline
   falls back to harmonic synthesis because the PVC is empty and the
   `acestep` Python package is not installed.
3. **alltalk uses hostPath** — not GitOps-managed, no PV/PVC lifecycle,
   cannot be recovered via standard Kubernetes storage primitives.
4. **image-warmer is inconsistent** — only warms container images for
   f5-tts, stable-diffusion, and alltalk; does not warm fish-speech or
   ace-step. Image warming is complementary to model prestage but
   serves a different purpose (fast pod startup vs. model availability).
5. **No ready-marker convention** — only fish-speech uses a `.ready.json`
   marker to signal that the model is fully staged.

## Decision

### Approved patterns

Three patterns are approved for ML model storage. A fourth (hostPath)
is deprecated for new workloads.

#### Pattern A: Static local PV + Prestage Job (preferred for dedicated models)

**Use when:** A workload has its own dedicated model that is not shared
with other workloads, and the model is large enough to warrant
dedicated storage.

**Reference implementation:** fish-speech-service

**Structure:**
```
apps/<service>/
  storage/
    pv.yaml          # Static local PV, Retain policy, nodeAffinity
    pvc.yaml         # RWO, bound to static PV
    kustomization.yaml
  prestage/
    model-prestage-job.yaml  # Job: download, verify, atomic promote
    kustomization.yaml
  workload/
    deployment.yaml  # Mounts PVC, HF_HUB_OFFLINE=1
    kustomization.yaml
  kustomization.yaml # resources: storage, prestage, workload
```

**Requirements:**
- Static local PV with `persistentVolumeReclaimPolicy: Retain`
- Node affinity to the GPU node(s) that will run the workload
- Prestage Job that:
  - Downloads from HuggingFace (or other source) to a staging directory
  - Verifies required files exist
  - Calculates checksums
  - Atomically promotes staging to final directory
  - Writes a `.ready.json` marker with timestamp, repo, revision
- Deployment sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`
- Flux Kustomization ordering: storage → prestage → workload
- Storage Kustomization uses `prune: false`, `deletionPolicy: Orphan`

**Advantages:**
- Fully GitOps-managed (PV, PVC, Job, Deployment all in Git)
- Reproducible model staging with checksums
- Ready marker enables programmatic verification
- Offline mode guarantees no runtime download attempts
- Prestage Job can be re-run to update models

**Disadvantages:**
- Requires node-local storage (cannot share across nodes)
- Prestage Job must run on the same node as the workload
- Model updates require re-running the prestage Job

#### Pattern B: NFS-shared PVC (preferred for shared HuggingFace cache)

**Use when:** Multiple workloads share the same HuggingFace model
cache, or workloads need to run on multiple nodes.

**Reference implementation:** shared-substrate hf-cache-pvc

**Structure:**
```
apps/shared-substrate/
  hf-cache-pvcs.yaml  # PVCs per namespace using nfs-client StorageClass
  kustomization.yaml

apps/<service>/
  workload/
    deployment.yaml   # Mounts hf-cache-pvc at /root/.cache/huggingface
```

**Requirements:**
- NFS-backed StorageClass (`nfs-client`) for ReadWriteMany access
- One PVC per namespace (not per workload)
- Workloads mount the shared PVC at `/root/.cache/huggingface`
- No `HF_HUB_OFFLINE` — workloads can download at runtime if cache misses
- HuggingFace's standard cache directory structure is used

**Advantages:**
- Shared cache reduces total storage and download bandwidth
- Workloads can run on any node (NFS is network-accessible)
- No prestage Job needed — first download populates the cache
- Simple to adopt — just mount the shared PVC

**Disadvantages:**
- NFS latency for model loading (slower than local storage)
- No ready marker or checksum verification
- Cache pollution risk (one workload's download may affect others)
- No offline guarantee — runtime downloads may still occur

#### Pattern C: Image-baked models (for small models only)

**Use when:** The model is small enough (< 500 MB) that baking it
into the container image is practical, and the model changes
infrequently.

**Requirements:**
- Model files are COPY'd into the image during build
- Image digest guarantees model immutability
- No PVC needed
- Model update requires a new image build

**Advantages:**
- Simplest pattern — no PVC, no prestage, no runtime download
- Model is pinned to the image digest (immutable)
- Works on any node without node-local storage

**Disadvantages:**
- Large images slow down pod scheduling and image pulling
- Model updates require a full image rebuild
- Image registry storage costs increase
- Not suitable for models > 500 MB

### Deprecated pattern

#### hostPath (deprecated for new workloads)

**Do not use for new workloads.** Existing hostPath workloads (alltalk-tts)
should migrate to Pattern A (static local PV + prestage Job) when
practical.

**Problems:**
- Not managed by Kubernetes PV/PVC lifecycle
- Cannot be recovered via standard storage primitives
- No GitOps visibility into the storage configuration
- Host directory must be manually created and populated
- No node affinity enforcement via PV

### Complementary: Image-warmer DaemonSet

The image-warmer DaemonSet is complementary to all patterns. It
pre-pulls container images to GPU nodes so that pod startup is fast.
It does NOT seed model files — that is the responsibility of the
prestage Job (Pattern A) or runtime download (Pattern B).

**Current state:**
- DaemonSet in `kube-system` with `nodeSelector: accelerator: nvidia`
- Containers: f5-tts-warmer, sd-warmer, alltalk-warmer
- Each container runs `sleep infinity` after the image is pulled

**Recommendation:** Add ace-step-service and fish-speech-service
containers to the image-warmer when they are deployed to GPU nodes.

### Selection criteria

```text
Is the model shared across workloads?
  Yes → Pattern B (NFS-shared PVC)
  No → Is the model < 500 MB?
         Yes → Pattern C (image-baked)
         No → Pattern A (static local PV + prestage Job)
```

### Ready-marker convention

Workloads using Pattern A should write a ready marker file after
prestage completes:

```json
{
  "ready": true,
  "timestamp": "2026-08-25T16:19:27Z",
  "model_repository": "org/model-name",
  "model_revision": "main",
  "manifest": { ... }
}
```

The deployment can optionally check for this marker in an initContainer
and fail fast if the model is not staged, rather than failing at
runtime with a cryptic download error.

## Application to ace-step-service

### Current state
- Static local PV (30Gi) at `/mnt/cluster_storage/k8s-models/ace-step-service`
- PVC mounted at `/root/.cache/huggingface/hub/`
- No prestage Job
- PVC is empty
- `HF_HUB_OFFLINE` is NOT set
- `acestep` Python package is not installed in the image

### Recommended changes

1. **Add a prestage Job** (Pattern A) that:
   - Downloads the ACE-Step 1.5 model from HuggingFace to the PVC
   - Verifies required checkpoint files
   - Writes a `.ready.json` marker

2. **Restore the `acestep` Python package** in the image by either:
   - Cloning ACE-Step-1.5 into the Dockerfile.f5-recovery build context
     and adding `pip install -e .`
   - Or vendoring the `acestep` package into the application repo
   - Or restoring the original `pytorch:...-acestep-prebuilt` base image

3. **Set `HF_HUB_OFFLINE=1`** in the deployment after the prestage Job
   has successfully populated the PVC

4. **Add ace-step-service to the image-warmer DaemonSet**

5. **Add an initContainer** that checks for the `.ready.json` marker
   and fails fast if the model is not staged

### Directory structure after changes
```
apps/ace-step-service/
  storage/
    pv.yaml
    pvc.yaml
    pvc-drop-zone.yaml
    kustomization.yaml
  prestage/
    model-prestage-job.yaml   # NEW
    kustomization.yaml        # NEW
  workload/
    deployment.yaml
    service.yaml
    scaledobject.yaml
    networkpolicy.yaml
    servicemonitor.yaml
    kustomization.yaml
  kustomization.yaml          # resources: storage, prestage, workload
```

## Consequences

- **New workloads** must choose from Patterns A, B, or C and document
  their choice in the deployment manifest comments or README.
- **Existing hostPath workloads** should plan migration to Pattern A.
- **f5-tts must either add a prestage Job or remove `HF_HUB_OFFLINE=1`**
  — the current state (offline mode + empty PVC) is broken.
- **Prestage Jobs should be versioned** (e.g., `model-prestage-v5`)
  and re-run when models are updated.
- **The image-warmer DaemonSet should be updated** when new GPU
  workloads are deployed.

## References

- [ADR-016: Persistent Storage Governance](ADR-016-persistent-storage.md)
  — established tiered storage classification (Tier 2: AI Models)
- [fish-speech prestage Job](../../../infrastructure/apps/fish-speech-service/prestage/model-prestage-job.yaml)
  — reference implementation for Pattern A
- [shared-substrate hf-cache PVCs](../../../infrastructure/apps/shared-substrate/hf-cache-pvcs.yaml)
  — reference implementation for Pattern B
- [image-warmer DaemonSet](../../../infrastructure/apps/governance-service/workload-warming/image-warmer.yaml)
  — complementary image pre-pull mechanism

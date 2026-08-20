# ADR-030: Model Caches Use Static Local PersistentVolumes on cortex

## Status
Accepted (Implemented)

## Context

The ToneRoot platform runs three GPU-governed model-cache workloads on the `cortex` node:
- `f5-tts-service` (F5-TTS model cache, 20 Gi)
- `fish-speech-service` (Fish Speech model cache, 20 Gi)
- `ace-step-service` (ACE-Step model cache, 30 Gi)

Each workload requires a PersistentVolumeClaim for its model-cache mount point (`/workspace/hf_home` or equivalent). The cluster uses K3s's bundled Local Path Provisioner (`rancher.io/local-path`) as the default storage class.

### Incident (2026-08-19)

Three dynamically provisioned `local-path` PVs were bound to PVCs in the `toneroot` namespace with `local.path` set to directories under `/mnt/cluster_storage/k8s-models/`. However:

1. The `local-path-config` ConfigMap is reconciled by the K3s addon controller to defaults (`/var/lib/rancher/k3s/storage`), which **wiped a custom `cortex` nodePathMap entry** pointing to `/mnt/cluster_storage/k8s-models`.
2. The provisioner's setup helper either failed to create the host directories or they were never created.
3. Kubelet refused to mount the non-existent paths, leaving all three pods stuck in `ContainerCreating` with `FailedMount` events.
4. Updating the provisioner ConfigMap only affects **future** dynamically provisioned claims — existing PVs are immutable records of the path selected at provisioning time.

The cluster is multi-node (`cortex`, `ran-ubuntu-inspiron`, `synapse`), and `cortex` is a K3s **agent**, not the server. A cluster-wide `default-local-storage-path` change would affect nodes that do not have the `/mnt/cluster_storage` mount.

### Requirements

- Model caches must reside on the 1 TB ext4 filesystem at `/mnt/cluster_storage` (mounted from `/dev/sdc1` on `cortex`).
- Storage binding must survive K3s addon reconciliation and node restarts.
- PVs must be constrained to `cortex` — no accidental scheduling on nodes lacking the host mount.
- Cache data is reproducible from upstream model sources; it is not the system of record.
- GitOps (FluxCD) must own the PV/PVC manifests.

## Decision

Model-cache workloads use **explicitly declared static `local` PersistentVolumes** whose host paths reside under `/mnt/cluster_storage/k8s-models/`.

### Binding contract

| Property | Value |
|----------|-------|
| PV type | `local` (host path) |
| `storageClassName` | `""` (empty — no dynamic provisioning) |
| PVC binding | `volumeName: <explicit-pv-name>` |
| `persistentVolumeReclaimPolicy` | `Retain` |
| `nodeAffinity` | `required`: `kubernetes.io/hostname In [cortex]` |
| PVC namespace | Explicit (`toneroot`) — not relying on Kustomize alone |
| Host path pattern | `/mnt/cluster_storage/k8s-models/<service-name>` |
| Host directory permissions | `0777` (recovery); tighten with `fsGroup` once ownership is established |
| GitOps management | PV + PVC manifests in `infrastructure/apps/<service>/` |

### Rejected options

1. **Editing the K3s-managed `local-path-config` ConfigMap directly**: The K3s addon controller reconciles this ConfigMap to defaults, wiping custom `nodePathMap` entries. Not durable.
2. **Global `default-local-storage-path` in K3s config**: Affects all nodes cluster-wide. `ran-ubuntu-inspiron` and `synapse` do not have `/mnt/cluster_storage/k8s-models`, making this unsafe for multi-node clusters.
3. **Dynamic `local-path` PVCs for model caches**: The allocation root and lifecycle are insufficiently explicit. The provisioner's ConfigMap is mutable by reconciliation, and dynamically provisioned PV paths are opaque (`pvc-<uid>_<ns>_<name>`).
4. **Networked persistent storage (NFS/NFS-client StorageClass)**: Adds operational complexity and network latency for large model reads. Unnecessary for reproducible model artifacts unless availability requirements change to require multi-node access.

## Consequences

### Positive
- **Durable binding**: Static PVs with `storageClassName: ""` and `volumeName` are immune to provisioner ConfigMap reconciliation.
- **Explicit scheduling constraint**: `nodeAffinity: cortex` prevents Kubernetes from scheduling consumers on nodes lacking the host mount.
- **Data retention on PVC deletion**: `Retain` policy ensures host data survives PVC deletion, requiring deliberate human review before cleanup.
- **GitOps ownership**: PV and PVC manifests are version-controlled and reconciled by FluxCD.
- **Predictable host paths**: `/mnt/cluster_storage/k8s-models/<service-name>` is operator-inspectable and survives reboots.

### Negative
- **`cortex` is an availability dependency**: F5-TTS, Fish Speech, and Ace Step cannot run if `cortex` is unavailable or the 1 TB volume is unmounted.
- **Node replacement requires data migration or cache rehydration**: Model caches must be copied to a replacement node or re-downloaded from upstream sources.
- **PV capacity is not a filesystem quota**: `spec.capacity.storage` is Kubernetes scheduling/accounting metadata, not an enforced ext4 quota. All three caches share the same 1 TB filesystem (currently 74% used, 235 GiB free).
- **`Retain` leaves orphaned host data**: Deleting a PVC does not delete the host directory. Operators must explicitly clean up retained directories.

### Neutral
- **`0777` permissions are a recovery posture**: Suitable for unblocking incidents; should be tightened with `securityContext.fsGroup` once container UIDs/GIDs are standardized.

## Evidence

### Implementation
- **PR**: https://github.com/architect-patternfoundry-systems/infrastructure/pull/19
- **Commit**: `fix(storage): replace dynamic local-path PVCs with static PVs for model caches`
- **Files changed**: `apps/{f5-tts-service,fish-speech-service,ace-step-service}/{pv.yaml,pvc.yaml,kustomization.yaml}`

### Validation (2026-08-19)
- All 3 static PVs: `Bound`, `Retain`, `nodeAffinity: cortex`, correct `local.path`
- All 3 PVCs: `Bound` to matching PVs, `storageClassName: ""`
- Filesystem: ext4 on `/dev/sdc1`, 916 GiB, 74% used (235 GiB free), 58M inodes free
- No `FailedMount` events on replacement pods after fix
- Kubelet mount phase passes (pods proceed past `ContainerCreating`)

### Incident evidence
- Broken PV/PVC YAML exported to `/tmp/pvc-recovery-evidence/`
- Maintenance event logged in `canvas_maintenance.db` (event ID: 1)

## Owner and Revision

| Field | Value |
|-------|-------|
| Owner | Platform Team (Infrastructure) |
| Author | Devin AI (incident response) |
| Date proposed | 2026-08-19 |
| Date accepted | 2026-08-19 |
| Revision | 1.0 |
| Approval state | Accepted (implemented during incident remediation) |
| Supersedes | None |
| Superseded by | None |

## Rollback / Exit condition

To revert this decision:
1. Scale consuming workloads to zero.
2. Delete the 3 static PVCs and PVs (Retain policy preserves host data).
3. Remove `pv.yaml` and `pvc.yaml` from GitOps manifests.
4. Either re-enable dynamic `local-path` provisioning (with a durable ConfigMap strategy) or migrate to networked storage.
5. Rehydrate model caches on the new storage backend.

Exit is warranted if:
- Multi-node model cache access becomes a requirement (migrate to NFS or shared filesystem).
- `cortex` is decommissioned and no replacement node with equivalent storage is available.
- Per-service filesystem quotas become necessary (migrate to a quota-enforcing storage system).

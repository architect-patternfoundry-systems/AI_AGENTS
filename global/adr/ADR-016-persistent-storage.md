# ADR-016: Persistent Storage Governance

## Context
The Sovereign Cluster operates in a dynamic "Interpose" workflow where tools like Tilt spin up and tear down environments dynamically over a stable baseline. This dynamic behavior increases the risk of PVC deletion during teardowns, which recently resulted in the loss of cached HuggingFace models. Furthermore, critical databases (`postgres`, `neo4j`) rely on standard provisioners (`nfs-client`, `local-path`) which default to a destructive `Delete` reclaim policy.

## Decision
We enforce a strict classification of Persistent Storage to prevent accidental data loss:

### Tier 1: Sovereign Data (Databases, MinIO, Neo4j, User Assets)
- MUST use `reclaimPolicy: Retain` (not just `archiveOnDelete`).
- Cannot rely on default `Delete` policies.
- For databases, `Retain` is mandatory because archive semantics do not apply to active DB state.
- **For dynamic NFS:** Future deployments must use the new `nfs-client-retained` StorageClass.
- **For `local-path`:** Use **static PV provisioning** instead of dynamic PVCs. Define the PV explicitly with `persistentVolumeReclaimPolicy: Retain` in your manifests. Dynamic provisioning with `local-path` is too risky for databases.

### Tier 2: Expensive Ephemeral (AI Models, Whisper Cache, SD Checkpoints)
- Because these take significant time/bandwidth to download, they MUST be protected from automated teardowns.
- `archiveOnDelete: "true"` is acceptable for Tier 2.
- Development namespaces managed by Tilt must annotate these PVCs with `tilt.dev/down-policy: keep`.
- *Note: `tilt.dev/down-policy: keep` only prevents Tilt from deleting the PVC; it doesn't change the PV's reclaim policy. Tier 1 workloads need BOTH the annotation AND the `Retain` policy.*

### Tier 3: True Ephemeral (Scratch space, logs)
- Allowed to use default `Delete` policies.

## Consequences
- **Data Safety:** The `reclaimPolicy: Retain` approach is the Kubernetes-native pattern for preventing data loss. When a PVC is deleted, the PV moves to a `Released` state but the data remains intact. An operator must manually delete the PV afterward, providing an explicit confirmation step before data destruction.
- **Operational Overhead:** Re-binding a `Released` PV requires manual administrative action to clear the PV's `claimRef`.

## Migration Note
When updating existing deployments to use the new PVC definitions, be aware that Kubernetes does not allow changing the `storageClassName` of a bound PVC. For existing Tier 1 workloads, the underlying PV must be manually patched to `persistentVolumeReclaimPolicy: Retain`.

### Migration Completed (June 22, 2026)

- **Method:** Option A (Clean Data Migration) via privileged Job
- **Job Name:** `pv-migration-job` (scheduled on `ran-ubuntu-inspiron`)
- **Backups:** `/mnt/backups/pv-migration/postgres-data-backup.tar.gz`, `neo4j-data-backup.tar.gz`
- **New Paths:**
  - Postgres: `/mnt/data/postgres-data` (local-path, nodeAffinity: ran-ubuntu-inspiron)
  - Neo4j: `/srv/nfs/k8s-data/neo4j-static` (NFS, server: ran-ubuntu-inspiron.tailc2cafc.ts.net)
- **Validation:** Postgres queries return 157 tables; Neo4j databases `neo4j` + `system` mounted
- **Cleanup Pending:** Delete old UUID PVs after 24h stability confirmation

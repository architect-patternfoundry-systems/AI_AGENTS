# ADR-016: GACS Data Retention and Storage Tiering

## Status
Accepted

## Context
The GraphAware Coordination Stack (GACS) uses Neo4j to map architectural topography (OpenTelemetry spans recording which services call, read from, or use other services). Historically, Neo4j was provisioned using an `nfs-client` StorageClass. This coupled the database's storage I/O directly to the cluster network overlay. During a recent network routing failure on the designated storage node, the storage I/O hung, causing Neo4j to panic to protect data integrity.

To adhere to the Sovereign Workflow and ensure operational resilience, we required a mechanism to decouple the database from network-dependent storage (Phase 2: Storage Isolation) while maintaining fiscal gravity and preventing the risk of local disk exhaustion.

An analysis of the database footprint revealed:
- **Graph Data (`/data/databases`)**: ~17 MB
- **Transaction Logs (`/data/transactions`)**: ~1.1 GB

The extremely high transaction-log-to-data ratio indicated a highly ephemeral, high-churn workload. This is structurally maintained by an active exponential decay pruning algorithm (`gacs-prune`) that deletes unreferenced edges older than 24 hours.

## Decision
We will implement a two-tier storage and retention architecture for GACS:

### 1. Storage Isolation (Warm Tier)
- **Action**: Migrate Neo4j from `nfs-client` to `local-path` storage on the `ran-ubuntu-inspiron` node.
- **Rationale**: Writing directly to the host's physical NVMe/SSD insulates the database from cluster network outages.
- **Mitigation**: To prevent local disk exhaustion (a runaway transaction log), we enforce a strict 7-day retention policy on Neo4j transaction logs (`db.tx.log.rotation.retention.policy="7 days"`). Given the 112GB headroom on the node and the 17MB steady-state graph size, the storage runway is effectively infinite.

### 2. Exponential Decay Pruning (Relevance Management)
- **Action**: Retain the existing `gacs-prune` hourly CronJob.
- **Rationale**: Structural telemetry older than a few days holds almost zero operational value for real-time mesh routing and coordination. The exponential decay algorithm perfectly maintains a lean, hyper-fast local dataset.

### 3. Cold Tier Archiving (Future Implementation)
- **Action**: Modify the `gacs-prune` CronJob to utilize the APOC plugin's export capabilities (`apoc.export.json.query`) before executing edge deletion.
- **Rationale**: Expiring graph structures will be streamed directly into a MinIO S3 bucket (e.g., `s3://gacs-archive/`). This establishes an infinite, cheap data lake for historical architectural auditing and AI model training without bloating the active Neo4j operational database.

## Consequences
- **Positive**: Neo4j becomes immune to CNI/Network overlay failures.
- **Positive**: Local disk exhaustion risk is mathematically bounded by strict transaction log rotation and structural pruning.
- **Negative**: The Neo4j pod is permanently pinned to `ran-ubuntu-inspiron`. If the node physically fails, the database graph is lost (though it will rebuild autonomously as new telemetry flows in).

# ADR-028: Service Delivery and Break-Glass Recovery Framework

## Status
Accepted (Certified Implementation Standard)

## Context
Multi-repository sovereign deployments separate application source code (`application`) from declarative GitOps manifests (`infrastructure`). In standard operation, Application CI builds immutable container images, publishes immutable digest-pinned tags to the canonical registry bridge (`registry-bridge.tailc2cafc.ts.net`), updates Kubernetes manifests in Git, and FluxCD reconciles cluster state.

However, during emergency break-glass incidents or when automated delivery is impaired, direct remediation must occur under strict cryptographic authorization, non-root execution, supply-chain verification, and durable audit retention without creating untracked cluster drift.

Furthermore, runtime dependency installations (such as dynamic `pip install` or `npm install` executed at container startup in air-gapped or network-isolated namespaces) fail catastrophically and violate the immutable container principle.

## Decision

We adopt the **Cryptographically Authorized, Rootless Break-Glass Delivery Framework** across all sovereign workload components (e.g. `tts-temporal-worker`, `gpu-nanny-controller`, `alltalk-tts`, etc.).

### 1. Delivery Model Separation
* **Standard Automated Delivery:** Application repositories own container builds and push immutable tags to `registry-bridge.tailc2cafc.ts.net`. Manifest updates are committed to Git, and FluxCD reconciles cluster state.
* **Immutable Containers (Zero Runtime Installs):** Workload containers must pre-bake all runtime dependencies into the container image. Dynamic runtime package installation inside running pods or entrypoints is strictly prohibited.
* **Secret Isolation:** Pull request validation runs in a secret-free stage. Automated PR and push triggers are strictly non-mutating (manifest rendering and schema validation only).
* **Guarded Break-Glass Recovery:** Emergency direct deployments must run as manual `workflow_dispatch` on `main`, require explicit boolean flags (`publish=true`, `deploy=true`), require a verified 40-character application commit SHA, enforce `production` environment review gates, and execute via the certified rootless runner.

### 2. 3-Stage Break-Glass Recovery Pipeline
The break-glass framework enforces a strict 3-stage lifecycle:
1. **Stage 1 (`prepare-release.sh`):** Isolated sandbox execution resolving OCI root index digests, platform descriptors (`linux/amd64`), and platform manifest digests; renders single Kustomize bundle and computes `rendered_bundle_sha256`.
2. **Stage 2 (`sign-release.sh`):** Authorization assembly attaching `approval_id`, `one_time_nonce`, `authorized_at`, and `ed25519` signature over canonical `jq -Sc '.envelope'` bytes. Enforces `cmp -s` byte-exact self-verification before releasing `release-record.json`.
3. **Stage 3 (`execute-breakglass.sh`):** Rootless runner execution engine enforcing 10 distinct phases with fail-closed security.

### 3. Execution Engine & Verification Gates
The rootless executor runs under UID `1000:1000` with dedicated scratch workspace management (`/work/breakglass`):
* **Preflight Self-Integrity:** Checks runner script checksum (`execute-breakglass.sha256`), schema checksum (`schema.sha256`), pinned binary versions (`kustomize v5.4.3`, `kubeconform v0.8.0`, `yq v4.44.3`, `crane v0.20.2`), and S3 Object Lock configuration (`ObjectLockEnabled == "Enabled"`).
* **Offline Strict Schema Check:** Evaluates `release-record.schema.json` via `jsonschema` (Draft 2020-12 with `FormatChecker`, `additionalProperties: false`, `$schema` const constraint).
* **Cryptographic Verification:** Validates raw 64-byte Ed25519 signature over canonical envelope.
* **Cluster & TTL Invariants:** Verifies live cluster context, API endpoint, namespace UID, and strict 60m TTL constraint.
* **Gate 0 (Deterministic OCI Platform Provenance):** Uses rootless Crane to verify:
  1. Root registry index digest matches signed `image_index_digest`.
  2. Index descriptor array contains exactly 1 descriptor for `linux/amd64` with valid image mediaType and empty variant (`variant == ""`).
  3. Selected descriptor digest matches signed `image_manifest_digest`.
  4. Platform config blob reports matching OS/architecture and OCI provenance labels (`org.opencontainers.image.revision`, `org.opencontainers.image.source`).
* **JIT Locking & Atomic Nonce Consumption:** Acquires lock ConfigMap (`breakglass-lock-<app>`) in `flux-system` JIT before execution. Idempotent no-op branch verifies runtime gates, writes `NO_CHANGE_VERIFIED` audit evidence, and preserves nonce. Mutation branch asserts `origin/main` freshness under lock, writes write-once nonce ConfigMap (`breakglass-nonce-<nonce>`), fast-forward pushes commit to Git, and reconciles single Flux Kustomization.
* **4-Gate Runtime Health Verification:**
  - **Gate 1 (Image Digest):** Live deployment container image matches signed immutable reference.
  - **Gate 2 (Rollout):** `rollout status` succeeds within 180s.
  - **Gate 3 (Pod Egress):** Executes in-pod network egress socket checks to cluster dependencies (Temporal, GPU Nanny, MinIO) bound to target ReplicaSet revision.
  - **Gate 4 (Telemetry):** Confirms retained application startup log telemetry strings.
* **Durable S3 WORM Audit Persistence:** Uploads structured evidence payload to remote MinIO S3 sink under `COMPLIANCE` retention mode (+90 days) and asserts `aws s3api get-object-retention` confirmation.

### 4. Non-Production Certification Standard (40 Test Matrix)
Before deployment to production, the break-glass tooling must satisfy the complete 40-scenario certification test matrix ([`run_certification_suite.sh`](file:///home/cortex/workspace/infrastructure/tools/breakglass/run_certification_suite.sh)), covering:
* TC-01 to TC-03: Mutation, Idempotent No-Op, Anti-Replay Nonce Protection.
* TC-04 to TC-08: Cryptographic Signature, Envelope Tampering, Unpinned Key Rejection, TTL & Cluster UID Protection.
* TC-09 to TC-16: Git Advancement, Registry Label Mismatch, Ambiguous Flux CD, Egress Failure, S3 Retention Verification, Lock Lifecycle, and Byte-Exact Canonicalization (`cmp -s`).
* TC-17 to TC-24: Offline Strict Schema Validation, Required Fields, Format Checks, Schema Checksum Pinning, and Package Integrity.
* TC-25 to TC-34: Supply-Chain Binary Checksums, Non-Root Execution, Wheelhouse Hash Locking, Executor Script Checksum Verification, and Workspace Isolation.
* TC-35 to TC-40: Multi-Platform Index Disambiguation, Platform Schema Enforcement, Descriptor Ambiguity Detection, Config OS/Arch Mismatch Detection, Descriptor MediaType Validation, and Empty Variant Enforcement.

## Consequences
* **Positive:** Complete elimination of arbitrary execution risks, unverified images, replay attacks, and container runtime installation failures.
* **Positive:** 100% GitOps alignment with FluxCD; emergency changes are committed and reconciled through declarative Git state.
* **Positive:** Legally defensible, tamper-evident WORM audit trail with cryptographic proof of authorization and runtime health.

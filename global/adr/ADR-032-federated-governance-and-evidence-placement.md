# ADR-032: Federated Governance & Multi-Plane Evidence Placement Architecture

## Status
Accepted (Platform Architecture Standard)

## Context
As our platform expands across sovereign clusters, GitOps pipelines, Temporal workflows, and human-in-the-loop review portals, maintaining a coherent and defensible audit boundary is vital. 

Historically, distributed systems face two common failure modes:
1. **The Monolithic CMDB Trap:** Attempting to duplicate every mutable cluster state, raw log stream, and Git blob into a central database, leading to stale copies, state drift, and high sensory tax.
2. **The Mutable Markdown Anti-Pattern:** Treating mutable wiki pages, dashboard UI state, or local terminal transcripts as authoritative proof of production execution.

We require an architectural invariant that strictly delineates where policy is defined, where decisions are sealed, where raw evidence is retained, where live metrics flow, and how human operators interact with the platform safely.

---

## Decision

We adopt the **Federated Governance & Multi-Plane Evidence Architecture**.

### 1. The Core Architectural Invariant

$$\text{Policy Intent} \ne \text{Runtime Fact} \ne \text{Governance Decision} \ne \text{UI Projection}$$

$$\text{Production Outcome} \iff \text{Authoritative Workflow Result} \land \text{Federated Evidence Manifest} \land \text{Authenticated Sign-off} \land \text{Signed Ledger Receipt}$$

$$\text{UI / Navigator Projection} \not\Rightarrow \text{Production Outcome}$$

> **Git defines intended policy and declarative controls; the runtime platforms (Kubernetes, Temporal, Cloudflare, Prometheus) report runtime facts; the management platform records authoritative runtime decisions and evidence manifests; content-addressed object storage preserves immutable raw artifacts; and user interfaces only render derived read-models and collect authenticated intent.**

---

### 2. Normative Platform Role Statement

The management platform is **authoritative** for:
- Governance state transitions and change lifecycle progression.
- Policy evaluation outcomes and entitlement decisions.
- Identity-bound approvals, role handoffs, and exception records.
- Evidence manifests and cryptographic receipt ledgers.
- Derived, reproducible read-model status projections.

The management platform is **not authoritative** for:
- Source code contents or build artifact binaries (owned by Git and OCI Registries).
- Kubernetes current API object state (owned by Kubernetes API).
- Temporal workflow execution history (owned by Temporal Server).
- Prometheus/Loki raw telemetry (owned by Prometheus/Loki/OTel backends).
- Cloudflare Access authentication assertions (owned by Cloudflare / IdP).
- Secret material, private keys, or workforce-sensitive source data (owned by KMS / Vault / IdP).

For each external system, the platform records a bounded, redacted, immutable reference: source identity, version/time-range, content or query digest, data classification, retention policy, producer identity, and verification result.

---

### 3. Multi-Plane Placement Matrix

| Plane | System of Record | Scope & Responsibilities | Mutability & Technical Controls |
|---|---|---|---|
| **Policy & Declarative Intent** | Git Repositories, ADRs, Policy-as-Code (OPA/Rego), IaC (OpenTofu) | Change policies, RASCI assignments, rollback plans, alert rule definitions, OpenTofu ingress. | Immutable **only** when referenced by full commit SHA, tree/blob SHA, or signed tag. Branch names (`main`) are mutable. |
| **Authoritative Governance Ledger** | PostgreSQL Ledger (`cmdb` schema) | Transactional state transitions, append-only event streams (`governance_event`), role bindings, cryptographic assertions (`change-closure-receipt/v1`). | Database-enforced `INSERT`-only; triggers block `UPDATE`/`DELETE`. Sequential aggregate hash chaining & periodic signed checkpoints. |
| **Raw Artifact & Evidence Store** | Content-Addressed Object Storage (MinIO / S3) | Large evidence exports, terminal Temporal workflow histories, raw telemetry query snapshots, container SBOMs. | Content-addressed keys (`sha256/xx/<digest>/...`), write-once, Object Lock / WORM retention locked. Dual-indexed. |
| **Runtime Observability** | Prometheus, Loki, OpenTelemetry | Live time-series metrics, log streams, synthetic probe records. | Time-bounded retention, aggregated rates/deltas, query-hash references, ingestion-level redaction. |
| **Workload Orchestration** | Kubernetes API, Temporal Server | Execution of container rollouts, scheduled mutations, long-lived workflows. | Controlled execution runtime; worker-mediated mutations; terminal workflow history exported before retention expiry. |
| **Presentation & UX** | Streamlit, Astro, Dev Landing Hub, Switchboards | Ephemeral read-models, interactive status projections, and collection of authenticated human intent. | Ephemeral, stateless with respect to authority; zero private keys or database write credentials. |

---

### 4. Content-Addressed Object Storage & Manifest Model

Raw evidence files are stored in object storage using deterministic digest paths rather than mutable human-friendly folders, accompanied by an explicit index structure:

```text
s3://governance-evidence/
  ├── sha256/c3/c3a0bbc4daeabae09f07a77b854158bbcbd3aba4af7792f7f566f21e4397ec9c/
  │     reconciliation-bundle.md
  ├── sha256/cd/cd5ef78f2c96c9b919db0c3b9789253fe3ee56baa146b7c92eb2071d28b3a16d/
  │     pilot-aar.md
  └── sha256/ef/ef56112a9c4501ba6f29910d8a0c4e1a0b32fc18a7792f7f566f21e4397ec9c/
        temporal-workflow-history.json

s3://governance-evidence-index/
  └── change/CR-2026-08-29-001/
        evidence-manifest.json
```

#### Evidence Manifest Schema (`evidence-manifest/v1`)

```json
{
  "schema_version": "evidence-manifest/v1",
  "manifest_id": "man-8f92a014-b812-4f33-912a-442a8b9f1021",
  "change_id": "CR-2026-08-29-001",
  "artifact_kind": "reconciliation_bundle",
  "content_sha256": "c3a0bbc4daeabae09f07a77b854158bbcbd3aba4af7792f7f566f21e4397ec9c",
  "content_addressed_uri": "s3://governance-evidence/sha256/c3/c3a0bbc4daeabae09f07a77b854158bbcbd3aba4af7792f7f566f21e4397ec9c/reconciliation-bundle.md",
  "source_git_commit": "229893beaaeeee19d84045a3b0729a0c935c1f6f",
  "source_blob_sha": "d88a729b4",
  "retention_class": "operations-restricted",
  "immutable_until": "2031-08-30T00:00:00Z",
  "verification_status": "VERIFIED"
}
```

#### Temporal Workflow History Retention & Export Contract
Temporal workflow history is durable during active execution, but subject to namespace retention limits. Closed workflow histories must be exported to content-addressed storage before retention expires:

```json
{
  "schema_version": "evidence-manifest/v1",
  "artifact_kind": "temporal_workflow_history",
  "workflow_namespace": "default",
  "workflow_id": "pgbouncer-scram-cutover/cr-2026-08-29-001-aad28c89",
  "workflow_run_id": "01a050d4-1044-79f2-a810-44e44d564859",
  "terminal_status": "COMPLETED",
  "history_export_sha256": "ef56112a9c4501ba6f29910d8a0c4e1a0b32fc18a7792f7f566f21e4397ec9c",
  "temporal_retention_expires_at": "2026-09-28T00:00:00Z",
  "export_verified_at_utc": "2026-08-30T00:15:00Z"
}
```

#### Class-Based Evidence Retention Policy
Evidence retention is governed by classification rather than a single blanket duration:

| Evidence Class | Example Artifacts | Retention & Protection Policy |
|---|---|---|
| **Operational Short-Term** | Raw Prometheus query exports, ephemeral pod traces | Time-bounded (e.g. 30–90 days); aggressive minimization & redaction. |
| **Change Evidence** | Reconciliation bundles, AARs, closure receipts, Temporal exports | WORM Object Lock based on change/audit policy (e.g. 5–7 years). |
| **Security Incident Evidence** | Ledger integrity failure dumps, access violation logs | Extended retention (7–10 years); Legal Hold capable. |
| **Build & Provenance** | Container SBOMs, in-toto attestations, image digest manifests | Retained for workload support lifecycle plus policy buffer. |
| **Workforce / Secret Data** | Passwords, bearer tokens, SCRAM verifiers, raw session payloads | **Strictly Prohibited** from storage in this plane. |

---

### 5. Append-Only Database Controls & Checkpoint Defense

The PostgreSQL governance ledger enforces immutability at the engine level through layered defense-in-depth:

```text
Append-Only Database Controls
  ├── Least-privilege application writer role (INSERT & SELECT only)
  ├── BEFORE UPDATE OR DELETE triggers raising hard exceptions
  ├── Per-event RFC 8785 canonical payload digest
  ├── Per-aggregate prior-event SHA-256 hash chaining
  ├── Periodic signed checkpoints (ledger-checkpoint/v1) signed via isolated key
  └── Checkpoint export to immutable WORM object storage
```

#### Event Schema Structure (`governance_event`)
- `event_id`: Unique monotonic identifier (`evt-...`).
- `event_type`: `CHANGE_WINDOW_OPENED`, `PREFLIGHT_COMPLETED`, `MUTATION_STARTED`, `MUTATION_COMPLETED`, `OBSERVATION_COMPLETED`, `CHANGE_CLOSED`, etc.
- `aggregate_id`: Target change identifier (e.g. `CR-2026-08-29-001`).
- `actor_subject_ref`: Validated immutable OIDC subject (`oidc-sub:...`).
- `policy_version_ref`: Pinned Git commit SHA of the governing policy.
- `canonical_payload_sha256`: RFC 8785 canonical digest.
- `prior_event_sha256`: Hash chaining reference.
- `signature_key_id`: Key identifier (`governance-sig-2026a`).
- `signature`: Server attestation signature (`ed25519-sig:...`).
- `evidence_manifest_id`: Linked content-addressed storage reference.
- `redaction_classification`: `OPERATIONS_RESTRICTED | SECURITY_RESTRICTED | PUBLIC`.

#### Independent Checkpoint Trust Boundary
```text
PostgreSQL Governance Writer
  └── Writes append-only events (INSERT & SELECT only)

Independent Integrity Verifier
  ├── Reads events & recomputes chain / aggregate tips
  ├── Builds canonical checkpoint payload (RFC 8785 UTF-8 bytes)
  ├── Requests signature from isolated signer / KMS (domain-separated signing input)
  ├── Stores checkpoint in WORM object storage (keyed by checkpoint_payload_sha256)
  └── Writes checkpoint manifest reference to ledger
```

#### Deterministic Canonicalization & Domain-Separated Signing Contract
To guarantee byte-level reproducibility across independent verifiers:
1. Construct a schema-valid JSON object excluding detached signature fields.
2. Canonicalize using **RFC 8785 JSON Canonicalization Scheme (JCS)**.
3. Encode canonical characters as **UTF-8 bytes**.
4. Compute **SHA-256** digest over those UTF-8 bytes (`checkpoint_payload_sha256`).
5. Construct domain-separated signing input: `governance-ledger-checkpoint/v1\n<checkpoint_payload_sha256>`.
6. Sign using isolated KMS/HSM key reference (`ed25519`).
7. Store canonical UTF-8 bytes at `s3://governance-evidence/sha256/<prefix>/<checkpoint_payload_sha256>/checkpoint.json`.

*Published Test Vectors:* The pilot suite publishes canonical test vectors (input JSON, RFC 8785 canonical UTF-8 hex/base64 bytes, SHA-256 digest, domain-separated signing input, public key, and expected signature outcome) to prevent cross-engine Unicode, numeric, or field-ordering discrepancies.

#### Periodic Signed Checkpoint Schema (`ledger-checkpoint/v1`)
Every 1,000 events or at daily cutover boundaries, an independent checkpoint verifier seals the ledger tip:

```json
{
  "schema_version": "ledger-checkpoint/v1",
  "checkpoint_id": "chk-912a44e4-b812-4f33-8f92-a014aa11021a",
  "created_at_utc": "2026-08-30T00:20:00Z",
  "verifier_identity": "spiffe://patternfoundry.internal/ns/governance/sa/ledger-integrity-verifier",
  "ledger_id": "governance-primary",
  "aggregate_scope": "all",
  "event_sequence_start": 1,
  "event_sequence_end": 194821,
  "event_count": 194821,
  "event_ordering_rule": "sequence_ascending",
  "chain_algorithm": "sha256",
  "chain_tip_sha256": "7a8f9c2d1b0e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a",
  "aggregate_root_algorithm": "sha256-merkle-v1",
  "aggregate_root_sha256": "c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3",
  "checkpoint_payload_sha256": "3f2b1a0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3a2b1c0d9e8f7a6b5c4d3e2f",
  "previous_checkpoint_payload_sha256": null,
  "canonicalization": "RFC8785",
  "payload_encoding": "utf-8",
  "payload_digest_algorithm": "sha-256",
  "signature_algorithm": "ed25519",
  "signature_input_format": "governance-ledger-checkpoint/v1\\n<checkpoint_payload_sha256>",
  "signing_key_id": "kms://governance-checkpoint-signer/key/2026a",
  "signature_encoding": "base64",
  "signature": "ed25519-sig:9f8e7d6c5b4a3a2b1c0d...",
  "content_addressed_uri": "s3://governance-evidence/sha256/3f/3f2b1a0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3a2b1c0d9e8f7a6b5c4d3e2f/checkpoint.json",
  "retention_class": "CHANGE_EVIDENCE",
  "verification_status": "VERIFIED"
}
```

*What each verification field proves:*
* **`chain_tip_sha256`**: Ordering, sequential continuity, and immutability from genesis.
* **`aggregate_root_sha256`**: Cryptographic Merkle root for efficient subset membership proofs.
* **`checkpoint_payload_sha256`**: Retrieval and byte-level integrity of the checkpoint artifact itself.
* **`signature`**: Authenticity of the independent verifier calculation.

---

### 6. Zero-Trust Interaction & Telemetry Minimization

1. **Identity & MFA Assurance:** Edge access is governed by Cloudflare Access with 1-hour bounded sessions and step-up MFA. The backend cryptographically validates `Cf-Access-Jwt-Assertion` on every sensitive action.
2. **Zero In-Process Secrets:** UI frontends (Streamlit) hold zero database write credentials, zero private signing keys, and zero direct Temporal cluster authority.
3. **Telemetry Minimization:** Telemetry records store reproducible PromQL/LogQL query definitions, execution time ranges, result hashes, and redacted exports. No raw passwords, SCRAM verifiers, DSNs, or request payloads may ever be stored in ledger events, Git repositories, AAR markdown files, or observability logs.

---

### 7. Drift Detection and Multi-Audience Referencing

#### 7.1 Drift-Control Objective
The platform **SHALL** detect, classify, evidence, and respond to material divergence between declared intent, governance records, retained evidence, and runtime state. It **SHALL NOT** infer that a system is healthy merely because no drift signal is present.

The response to drift **SHALL** be strictly risk-classified:

| Drift Class | Default Response | Rationale |
|---|---|---|
| **GitOps-managed low-risk application spec drift** | Detect and optionally auto-reconcile through Flux | Git is intended source; controlled reconciliation is standard. |
| **Sensitive auth/RBAC/network policy drift** | Detect, alert, pause dependent workflows, require governed remediation | Auto-reapply can worsen an incident or erase forensic evidence. |
| **OpenTofu-managed cloud edge drift** | Detect with read-only `tofu plan -refresh-only`; require reviewed apply | Avoids accidental state writes or unreviewed cloud changes. |
| **Governance-ledger hash mismatch** | Freeze affected operations, open security incident (`INC-*-*`), preserve evidence | A hash-chain failure is an integrity event, not an auto-fix candidate. |
| **Object-evidence digest mismatch** | Quarantine reference, retry from replica, open evidence-integrity incident | Never overwrite potentially relevant evidence automatically. |
| **Telemetry gap / collector failure** | Mark evidence incomplete, block confidence-sensitive closure | Missing data is not healthy data. |
| **UI projection drift** | Rehydrate projection from ledger/source systems | Safe to rebuild immediately because UI state is non-authoritative. |

#### 7.2 Standardized Drift Observation Schema (`drift-observation/v1`) & Normalization Behavior
Drift events are recorded as first-class append-only observations:

```json
{
  "schema_version": "drift-observation/v1",
  "observation_id": "drf-7a19c4e4-b812-4f33-912a-0014aa11021b",
  "observed_at_utc": "2026-08-30T00:20:00Z",
  "source_system": "flux",
  "target_type": "kubernetes_resource",
  "target_ref": "deployment/default/governed-intentionality-daemon",
  "intent_ref": {
    "repository": "architect-patternfoundry-systems/neural_mesh_canvas",
    "commit_sha": "229893beaaeeee19d84045a3b0729a0c935c1f6f",
    "blob_or_tree_sha": "d88a729b4"
  },
  "drift_class": "SENSITIVE_AUTHORIZATION",
  "severity": "HIGH",
  "observed_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "expected_digest": "c3a0bbc4daeabae09f07a77b854158bbcbd3aba4af7792f7f566f21e4397ec9c",
  "normalization_algorithm": "k8s-spec-strip-runtime-v1",
  "evidence_manifest_ref": "man-8f92a014-b812-4f33-912a-442a8b9f1021",
  "response_policy": "ALERT_AND_PAUSE",
  "response_status": "PAUSED",
  "incident_ref": "INC-2026-08-30-001",
  "resolved_by_event_ref": null
}
```

*Normalization Specification (`k8s-spec-strip-runtime-v1`):*
* Strips `.metadata.uid`, `.metadata.resourceVersion`, `.metadata.generation`, `.metadata.creationTimestamp`, `.metadata.managedFields`, `.metadata.ownerReferences`, runtime annotations, and `.status`.
* Sorts key-value maps (labels, annotations) lexicographically.
* Preserves order for semantically ordered lists (container arguments, environment variable arrays, volumes, ports).
* Prohibits hashing unmasked secret material.

*Allowed Enumerations:*
* **`drift_class`**: `LOW_RISK_CONFIGURATION`, `RUNTIME_AVAILABILITY`, `SENSITIVE_AUTHORIZATION`, `SECRET_MATERIAL`, `INTEGRITY_FAILURE`, `POLICY_NONCOMPLIANCE`
* **`response_policy`**: `OBSERVE_ONLY`, `ALERT`, `ALERT_AND_PAUSE`, `RECONCILE_APPROVED`, `QUARANTINE`, `REQUIRE_HUMAN_AUTHORIZATION`
* **`response_status`**: `OBSERVED`, `PENDING_REVIEW`, `PAUSED`, `RECONCILIATION_QUEUED`, `RECONCILED`, `QUARANTINED`, `RESOLVED`, `FAILED`

#### 7.3 Continuous Verification Loops
1. **Declarative-State Verification:** Flux and OpenTofu read-only plans compare managed live state to pinned Git intent. The platform records source revisions, observation timestamps, diffs or digest summaries, and the policy-selected response.
2. **Ledger Integrity Verification:** An independent verifier recomputes aggregate chains and validates periodic signed checkpoints exported to immutable evidence storage.
3. **Evidence Integrity Verification:** Scheduled jobs retrieve digest-addressed objects and compare raw-byte checksums to signed evidence-manifest records.
4. **Schema-Contract Verification:** CI and database contract checks (Soda SQL / custom linters) validate versioned schemas, constraints, and relational invariants.
5. **Runtime Endpoint Verification:** Synthetic probes verify expected endpoint, certificate, and listener behavior using approved, non-secret test identities.

#### 7.4 Six Canonical Implementation Contracts

| Contract | Purpose & Authority Boundary | Identifier Grammar (UUIDv4 & UUIDv7) |
|---|---|---|
| `governance-event/v1` | Append-only decision, role handoff, and change lifecycle transition. | `^evt-[0-9a-f]{8,16}$` |
| `evidence-manifest/v1` | Binds a source artifact/export to content digest, storage location, classification, retention, and verification state. | `^man-[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` |
| `ledger-checkpoint/v1` | Independently signed integrity checkpoint sealing the ledger tip. | `^chk-[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` |
| `drift-observation/v1` | Normalized drift detection result with risk-classified response status. | `^drf-[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` |
| `governance-decision-view/v1` | Redacted, capability-scoped API projection for human operators and AI agents. | `^gdv-[0-9a-f]{8,16}$` |
| `offline-audit-package/v1` | Export index and offline verifier metadata for independent compliance audits. | `^pkg-[0-9a-f]{8,16}$` |

Every schema strictly defines `schema_version`, canonicalization (RFC 8785), digest algorithm (SHA-256), ID formats, clock sources, classification, producer identity, source system, verification status, policy reference, retention class, signature requirements, and redaction constraints. Unknown versions return `UNSUPPORTED_SCHEMA`.

#### 7.5 Multi-Audience Interface Contract
- **Human Operators:** Portals present read-only, redacted, source-timestamped projections unless an authenticated server-defined intent is explicitly available.
- **Autonomous AI Agents:** Machine interfaces provide typed, versioned schemas (`governance-decision-view/v1`) with verification status, source reference, policy version, and permitted actions. Agents consume verified digests **plus** typed semantic policy context.
- **CI/CD Pipelines:** Ingress gates fail closed for unresolved required policy, artifact, schema, or dependency references.
- **Auditors:** Export packages contain signed receipts, evidence manifests, immutable artifact references, and offline verification instructions.

```json
{
  "schema_version": "governance-decision-view/v1",
  "source_ref": {
    "uri": "s3://governance-evidence/sha256/c3/c3a0bbc4daeabae09f07a77b854158bbcbd3aba4af7792f7f566f21e4397ec9c/reconciliation-bundle.md",
    "sha256": "c3a0bbc4daeabae09f07a77b854158bbcbd3aba4af7792f7f566f21e4397ec9c"
  },
  "verification_status": "VERIFIED",
  "semantic_type": "change-closure-receipt/v1",
  "policy_version": "post-closure/v1",
  "allowed_agent_actions": [
    "READ_STATUS",
    "REQUEST_RECONCILIATION"
  ]
}
```

---

### 8. Reference Implementation Pilot Protocol & Success Criteria

Before applying this framework across all workloads, a single reference application executes the validation drill against **10 executable success criteria**.

#### 8.1 Pilot Execution Scope & Safety Boundaries
* **Single Workload Scope:** One reference workload in a dedicated pilot namespace (`test-governance-pilot`), one repository, one immutable container digest, one ledger instance, one isolated signer, and one WORM evidence bucket prefix.
* **Safety Invariants:**
  * Low-risk reconciliation runs solely against synthetic allowlisted fields.
  * Sensitive authorization drift uses a dedicated test `RoleBinding`/`ServiceAccount`; production access controls are never mutated for testing.
  * Quarantine tests write mismatched test objects to pilot-only evidence keys; existing valid evidence is never overwritten.
  * Telemetry loss tests use isolated mock ingestion streams; production monitoring is never suppressed.

#### 8.2 Dependency-Aware 10-Step Implementation Order
| Order | Pilot Capability Increment | Criteria Enabled |
|---:|---|---|
| **1** | Contract validators and identifier/canonicalization test vectors | Foundation for all criteria |
| **2** | Append-only event store and independent reconstruction tool | Criteria 1, 3 |
| **3** | Isolated signer and signed checkpoint writer | Criterion 3 |
| **4** | WORM/object-lock evidence persistence and digest retrieval verifier | Criteria 4, 8 |
| **5** | Immutable container / Git intent correlator | Criteria 1, 2 |
| **6** | Stateless decision-view projection and rebuild verifier | Criterion 5 |
| **7** | Drift normalizer, classifier, and policy executor | Criteria 6, 7 |
| **8** | Telemetry completeness evaluator | Criterion 9 |
| **9** | Offline audit-package generator and air-gapped verifier | Criterion 10 |
| **10** | Integrated adversarial test run | All criteria, including adverse failure paths |

#### 8.3 Object-Store WORM Storage Proof Protocol
1. Write checkpoint object with declared retention class and retain-until date.
2. Attempt overwrite at the same digest-addressed key $\rightarrow$ verify rejection.
3. Attempt delete using standard writer credentials $\rightarrow$ verify rejection.
4. Attempt retention shortening using writer credentials $\rightarrow$ verify rejection.
5. Verify authorized retention/legal-hold actor behaves according to Governance/Compliance mode.
6. Record storage configuration, object version ID, retention mode, and observed API response in evidence manifest:
   ```json
   {
     "storage_backend": "s3-compatible",
     "bucket": "governance-evidence-pilot",
     "object_key": "sha256/3f/3f2b1a0e.../checkpoint.json",
     "object_version_id": "v-912a44e4-001",
     "object_lock_mode": "GOVERNANCE",
     "retain_until_utc": "2026-09-30T00:00:00Z",
     "legal_hold_status": "OFF"
   }
   ```

#### 8.4 Pilot Success Criteria & Objective Proof Matrix

| Criterion | Minimum Objective Proof | Required Test Record Artifact |
|---|---|---|
| **1. Git Intent Reference** | Verify full commit ID plus immutable blob/tree object; reject branch-only references. | `Test ID`, `Input fixture`, `Expected result`, `Observed result`, `Evidence manifest ID`, `Checkpoint ID`, `Source commit`, `Container digest`, `Verifier version`, `Timestamp`, `Actor identity`. |
| **2. Immutable Container** | Confirm registry digest equals Git deployment digest equals pod image ID. | Verified container digest manifest. |
| **3. Ledger Reconstruction** | Offline tool recomputes chain/root from export and verifies checkpoint signature. | Signed checkpoint export verification receipt. |
| **4. Digest Retrieval** | Fetch content-addressed checkpoint/evidence object and recompute exact SHA-256. | Exact byte digest match log. |
| **5. Stateless UI Proof** | Delete projection/cache; rebuild from source and compare deterministic view digest. | Identical pre/post projection hash match. |
| **6. Controlled Reconcile** | Low-risk drift produces approved reconciliation request and only changes allowlisted fields. | Flux reconciliation log with bounded diff. |
| **7. Governed Pause** | Sensitive drift produces alert/pause and blocks dependent changes. | Paused workflow state & high-severity incident ref. |
| **8. Quarantine** | Deliberately wrong digest creates immutable incident/quarantine evidence without overwriting source or target. | Quarantine record in `s3://governance-evidence-index/quarantine/`. |
| **9. Confidence Incomplete** | Simulate telemetry loss; closure state explicitly becomes incomplete rather than passing. | Incomplete evidence evaluation assertion. |
| **10. Offline Audit** | Air-gapped verifier checks exports, canonicalization, hashes, signatures, object manifests, and policy metadata. | Standalone offline verification pass. |

#### 8.5 Formal Pilot Exit Closure Record
Broad fleet adoption requires one signed, immutable closure record containing:
* Pilot workload ID and dedicated namespace.
* Source commit SHA and blob/tree SHA.
* Container tag and immutable digest.
* Contract schema versions (`v1`).
* Verifier version and container digest.
* Signer key ID and signature algorithm (`ed25519`).
* Checkpoint ID and payload SHA-256.
* Evidence manifest IDs and object URIs.
* Object-lock mode and verified retention settings.
* Telemetry completeness verification result.
* Full test matrix results (all 10 criteria passing).
* Independent reviewer sign-off assertion.

---

## Consequences

### Positive
- **Guaranteed Provenance:** Every production outcome is corroborated across 5 independent planes with cryptographic verification.
- **Differentiated Drift Governance:** Prevents unsafe automated overwrites while maintaining continuous visibility.
- **Scalable Architecture:** High-volume raw blobs reside in retention-locked object storage, keeping transactional ledger tables performant and clean.
- **Semantic Safety for Agents:** AI agents receive typed, versioned policy context alongside cryptographic integrity proofs.

### Negative / Trade-offs
- Requires strict discipline in structuring changes, runbooks, and alert rules into their respective repositories.
- Requires maintenance of content-addressed object storage retention locks and periodic restore-verification drills.

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

> **Git defines intended policy and declarative controls; the management platform records authoritative runtime decisions and evidence manifests; content-addressed object storage preserves immutable raw artifacts; observability systems retain operational telemetry; and user interfaces only render and collect authenticated intent.**

$$\text{Production Outcome} \iff \text{Authoritative Workflow Result} \land \text{Federated Evidence Manifest} \land \text{Authenticated Sign-off} \land \text{Signed Ledger Receipt}$$

$$\text{UI / Navigator Projection} \not\Rightarrow \text{Production Outcome}$$

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
| **Policy & Declarative Intent** | Git Repositories, ADRs, Policy-as-Code | Change policies, RASCI assignments, rollback plans, alert rule definitions, OpenTofu ingress. | Immutable by Git commit SHA / tag; changes require PR reviews. |
| **Authoritative Governance Ledger** | PostgreSQL Ledger (`cmdb` schema) | Transactional state transitions, append-only event streams (`governance_event`), role bindings, cryptographic assertions (`change-closure-receipt/v1`). | Database-enforced `INSERT`-only; trigger blocks `UPDATE`/`DELETE`. Sequential aggregate hash chaining. |
| **Raw Artifact & Evidence Store** | Content-Addressed Object Storage (MinIO / S3) | Large evidence exports, workflow execution histories, raw telemetry query snapshots, container SBOMs. | Content-addressed keys (`sha256/xx/<digest>/...`), write-once, Object Lock / WORM retention locked. |
| **Runtime Observability** | Prometheus, Loki, OpenTelemetry | Live time-series metrics, log streams, synthetic probe records. | Time-bounded retention, aggregated rates/deltas, query-hash references, data minimization. |
| **Workload Orchestration** | Kubernetes API, Temporal Server | Execution of container rollouts, scheduled mutations, long-lived workflows. | Controlled execution runtime; strictly worker-mediated mutations. |
| **Presentation & UX** | Streamlit, Astro, Dev Landing Hub | Stateless renderers of server-provided read models and collection of authenticated human intent. | Ephemeral, stateless with respect to authority; zero private keys or write credentials. |

---

### 4. Content-Addressed Object Storage & Manifest Model

Raw evidence files are stored in object storage using deterministic digest paths rather than mutable human-friendly folders:

```text
s3://governance-evidence/
  ├── sha256/c3/c3a0bbc4daeabae09f07a77b854158bbcbd3aba4af7792f7f566f21e4397ec9c/
  │     reconciliation-bundle.md
  └── sha256/cd/cd5ef78f2c96c9b919db0c3b9789253fe3ee56baa146b7c92eb2071d28b3a16d/
        pilot-aar.md
```

#### Evidence Manifest Schema (`evidence-manifest/v1`)

```json
{
  "schema_version": "evidence-manifest/v1",
  "manifest_id": "man-8f92a014-b812-4f33-912a-442a8b9f1021",
  "change_id": "CR-2026-08-29-01",
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

---

### 5. Append-Only Database Controls

The PostgreSQL governance ledger enforces immutability at the database engine level:

1. **Role Separation:** Application service accounts hold `INSERT` and `SELECT` grants only.
2. **Immutability Triggers:** `BEFORE UPDATE OR DELETE` triggers raise database exceptions on `governance_event` and `evidence_manifest` tables.
3. **Aggregate Hash Chaining:** Every event includes the SHA-256 digest of the previous event for that aggregate (`prior_event_sha256`), forming a tamper-evident hash chain.
4. **Correction Linking:** Corrections or amendments are committed as new events referencing `supersedes_event_id` or `amends_event_id`.

#### Event Schema Structure (`governance_event`)
- `event_id`: Unique monotonic identifier (`evt-...`).
- `event_type`: `CHANGE_WINDOW_OPENED`, `PREFLIGHT_COMPLETED`, `MUTATION_STARTED`, `MUTATION_COMPLETED`, `OBSERVATION_COMPLETED`, `CHANGE_CLOSED`, etc.
- `aggregate_id`: Target change identifier (e.g. `CR-2026-08-29-01`).
- `actor_subject_ref`: Validated immutable OIDC subject (`oidc-sub:...`).
- `policy_version_ref`: Pinned Git commit SHA of the governing policy.
- `canonical_payload_sha256`: RFC 8785 canonical digest.
- `prior_event_sha256`: Hash chaining reference.
- `signature_key_id`: Key identifier (`governance-sig-2026a`).
- `signature`: Server attestation signature (`ed25519-sig:...`).
- `evidence_manifest_id`: Linked content-addressed storage reference.
- `redaction_classification`: `OPERATIONS_RESTRICTED | SECURITY_RESTRICTED | PUBLIC`.

---

### 6. Zero-Trust Interaction & Telemetry Minimization

1. **Identity & MFA Assurance:** Edge access is governed by Cloudflare Access with 1-hour bounded application sessions and step-up MFA. The backend validates `Cf-Access-Jwt-Assertion` cryptographically on every sensitive action.
2. **Zero In-Process Secrets:** UI frontends (Streamlit) hold zero database write credentials, zero private signing keys, and zero direct Temporal cluster authority.
3. **Telemetry Minimization:** Telemetry records store reproducible PromQL/LogQL query definitions, execution time ranges, result hashes, and redacted exports. No raw passwords, SCRAM verifiers, DSNs, or request payloads may ever be stored in ledger events, Git repositories, AAR markdown files, or observability logs.

---

## Consequences

### Positive
- **Guaranteed Provenance:** Every production outcome is corroborated across 5 independent planes with cryptographic verification.
- **Drift Prevention:** Dashboards and local CLI tools are proven to be non-authoritative read projections, eliminating false execution claims.
- **Scalable Architecture:** High-volume raw blobs reside in retention-locked object storage, keeping transactional ledger tables performant and clean.

### Negative / Trade-offs
- Requires strict discipline in structuring changes, runbooks, and alert rules into their respective repositories.
- Requires maintenance of content-addressed object storage retention locks and periodic restore-verification drills.

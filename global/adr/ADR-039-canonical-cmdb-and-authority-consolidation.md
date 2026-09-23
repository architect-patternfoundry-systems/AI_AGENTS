# ADR-039: Canonical CMDB & Source-Authority Consolidation (Aegis Control Plane)

## Status

**Accepted** — 2026-09-23 (governance review; scope: minimum durable authority
model for v0.2 persistence). The broader canonical-data-model items remain
directional until their own acceptance gates are met (see *Deferred*).

## Decision statement

> Aegis Control Plane will use Postgres as an **append-only observation,
> provenance, and reconciliation-evidence plane** before it becomes a canonical
> CMDB or change-execution authority. `mydatabase.service_management` remains
> the planned canonical CI/service nucleus; a new `governance` schema will
> store source snapshots, collection runs, source-derived candidates, and open
> reconciliation findings. The initial collector may insert only into the
> observation plane and may not update or delete evidence, transition findings,
> create canonical CIs, or mutate external systems. Any canonicalization,
> disposition, execution, verification, or closure action requires separately
> designed authorization, evidence, and database roles.

The framing question answered by this ADR is not "where do we put the data?"
but: **what is the first durable write Aegis is allowed to make, what does that
write mean, and what powers does it explicitly not grant?**

## Context

A workspace gap analysis (`aegis-control-plane/docs/reports/gap-report.md` and
`gap-report-review-addendum.md`, 2026-09-22) inspected the documented HA/DR MDM
design against live state and found a **control-plane convergence problem**,
not a missing-schema problem:

- **4+ parallel systems of record with no reconciliation rule:**
  `devops_platform` CMDB (23 CIs), `mydatabase.service_management` (typed CMDB,
  4 CIs), three SQLite stores (`access_ontology.db`, `data/cmdb_governance.db`,
  `devops_platform.db`), `config/app-intent.yaml`, and OpenTofu
  `envs/prod/main.tf`. The `aegis-control-plane` v0.1.0-alpha.1 adapter run
  measured the edge boundary precisely: **48 declared edge apps, 30 open
  findings, 25 host-local placeholder origins**.
- **Evidence-integrity failure:** `CR-20260830-TONEROOT-DATA-001` is rendered
  by the governance-closure portal as a production cutover, but is a synthetic
  fixture simulation (`generate_seed_data()`; no DB connection;
  placeholder-grade `ed25519-sig:` values of 12 bytes vs. the required 64).
  `governance.delta_ledger`, its roles, functions, and migration do not exist.
- **Dormant durable path:** `governance_cert.governance_audit_events` exists
  (migration 002 applied) but is empty because `GOVERNANCE_AUDIT_DSN` is unset.
- **Live data drift:** `mydatabase.public.domains` disagrees with the OpenTofu
  domain portfolio on 4 of 7 records; two domains approach expiry.
- **Tier-0 recovery loop:** OpenTofu state (`s3://opentofu-state`) resides on
  the cortex-pinned local-SSD MinIO — the failure domain implicated in the
  2026-09 cluster-wide ImagePullBackOff cascade (CortexRebootReport).

ADR-032 already defines the federated evidence model (PostgreSQL governance
ledger, content-addressed object storage, Git/IaC intent, UI as
non-authoritative projection). `aegis-control-plane` v0.1.0-alpha.1
demonstrated the read-only collection boundary end-to-end (bounded parser →
provenance candidates → open findings → schema-validated contracts). What is
missing is the **minimum durable authority decision** governing what may be
persisted, and under what constraints.

## Decision

### 1. Canonical nucleus

**`mydatabase.service_management` is the eventual canonical service/CI
nucleus.** It is evolved in place; no new `mdm_db` is introduced;
`devops_platform` and the SQLite mirrors are not canonical.

Rationale: it is already typed (`ci_type`/`criticality` enums, lifecycle,
owner, environment, namespace, cluster attributes), is the closest existing
fit to the intended MDM domain, and a third Postgres database would create
another authority boundary before the existing two are reconciled.

**Constraint:** this decision does *not* make source-derived candidate records
canonical `configuration_item` records. That promotion requires an explicit
later governance decision (see *Deferred*).

### 2. First persistence target

A dedicated **`governance` schema** in `mydatabase` — alongside, not inside,
`service_management` — holds the Aegis observation/evidence plane:

| Table | Purpose | Initial writer |
|---|---|---|
| `governance.source_snapshot` | Immutable identity/metadata for one collected source artifact | Aegis collector |
| `governance.collection_run` | One collector execution incl. boundary/provenance metadata | Aegis collector |
| `governance.observation_candidate` | Source-derived candidate record captured during a run | Aegis collector |
| `governance.reconciliation_finding` | Open discrepancy identified in a run | Aegis collector |
| `governance.finding_evidence` | Content-addressed evidence references for a candidate/finding/run | Aegis collector |
| `governance.finding_transition` | Reserved for future human/governance-controlled transitions | **No initial writer** |

This avoids polluting the canonical CMDB with unreviewed parser output and
avoids burying collection history inside generalized `attributes jsonb`.

### 3. Relationship to `service_sync_ledger`

`service_sync_ledger` is retained as the existing operational
synchronization/checkpoint ledger; it is **not** replaced or repurposed in the
first persistence work. Separation of meaning:

| Concept | Store | Meaning |
|---|---|---|
| Ingestion checkpoint / cursor | `service_sync_ledger` | "Did this sync process reach a source position?" |
| Immutable collection provenance | `governance.collection_run` + `source_snapshot` | "Which exact bytes and collector boundary were observed?" |
| Discrepancy | `governance.reconciliation_finding` | "What declared-vs-compared mismatch did this run detect?" |
| Human disposition | Future `governance.finding_transition` | "Who accepted, suppressed, resolved, or superseded, and why?" |

### 4. Candidate versus canonical identity

Four identifier layers are maintained; none may be overloaded into another:

| Identifier | Owner | Meaning | Auto-generated? |
|---|---|---|---|
| `run_id` | Collector | One collection execution | Yes |
| `source_snapshot_id` | Aegis evidence plane | A specific source artifact/version observed | Yes |
| `candidate_id` | Collector contract | Deterministic source-derived identity | Yes |
| `canonical_ci_id` | Service-management authority | Approved, durable CI identity | **No — not in v0.2** |

Supporting rules:

- `candidate_supersedes_candidate_id` records source-coordinate changes or
  renewed discovery.
- `canonical_ci_id` is a **nullable external reference only** — it is *not* a
  foreign key until canonical CI placement and identifier generation are
  decided.
- Future linkage requires `matching_confidence` + `matching_basis` produced by
  an explicit matching/curation workflow.
- No automatic identity merge based solely on FQDN, service name, port, or IaC
  locator — the control against false consolidation.

### 5. Retention, redaction, and evidence

Structured provenance and content hashes persist in Postgres; raw source
artifacts live under a controlled retention policy:

| Artifact | Postgres storage | Raw-content policy |
|---|---|---|
| Source revision/worktree metadata | Store | Always |
| SHA-256 and byte count | Store | Always |
| Parsed normalized candidate/finding fields | Store | Always, after classification/redaction |
| Raw HCL/YAML input | Reference + hash | Private object storage if needed for reproducibility; never in public repo |
| Cloudflare/runtime API responses | Reference + hash | Least-privilege extracts only; redact credentials/account IDs/private endpoints |
| Sensitive evidence | Hash + classification + access pointer | Restricted object storage; no unrestricted DB blobs |
| Change/approval artifacts | Not in this phase | Future governance/evidence design |

Invariant:

```text
DB record = normalized fact + provenance + content hash + controlled evidence pointer
DB record ≠ unbounded raw artifact blob
```

Retention: run metadata and normalized findings — indefinitely (small volume);
raw snapshots — 90 days default, longer for incident/change evidence;
superseded findings — indefinitely with successor links; suppressions —
indefinitely including expiry/review history; secrets — never ingested (fail
or redact before persistence).

### 6. Append-only policy

Initial Aegis persistence is **append-only for observed evidence and
collector-generated findings**:

- The collector role gets `INSERT` on observation tables and restricted
  `SELECT` only as required for idempotency.
- It gets **no** `UPDATE`, `DELETE`, DDL, or privileges on
  `service_management.configuration_item`.
- Collection records use immutable `run_id`s and source snapshot hashes.
- Repeated identical observations are not destructive updates: new observation
  instances, or deduplication under an explicit idempotency key with retained
  last-observed linkage.
- A separate governance role — distinct from the collector role — owns
  transitions and canonicalization.
- Database triggers reject `UPDATE`/`DELETE` on immutable observation records.

This is the technical enforcement of "the collector has no authority."

## Conceptual schema shape (guides first migration; not final DDL)

```text
governance.source_snapshot
  source_snapshot_id, source_system, source_locator, source_revision,
  revision_claim, source_sha256, byte_count, worktree_clean,
  collected_at, classification, evidence_uri, retention_until

governance.collection_run
  run_id, collector_name, collector_version, started_at, completed_at,
  parse_mode, parse_confidence, coverage_notes_json,
  source_snapshot_id, idempotency_key, status

governance.observation_candidate
  observation_candidate_id, run_id, candidate_id, source_snapshot_id,
  candidate_type, normalized_payload_json, candidate_sha256,
  canonical_ci_id NULL, observed_at

governance.reconciliation_finding
  finding_id, run_id, finding_type, severity,
  reconciliation_state = 'open',
  subject_candidate_id, compared_candidate_id NULL,
  finding_payload_json, finding_sha256, observed_at,
  supersedes_finding_id NULL

governance.finding_evidence
  finding_evidence_id, finding_id, evidence_ref, evidence_sha256,
  classification, recorded_at
```

## Acceptance conditions (the "shall" statements this ADR satisfies)

1. **Authority** — Declared edge config: OpenTofu. Runtime observation:
   Cloudflare/Kubernetes/DNS/registrar collectors (future). Canonical CI
   identity: `service_management` authority (future curation). Human
   disposition: `finding_transition` (future role).
2. **Write scope** — The first collector shall write only the five
   `governance` observation tables and shall be technically unable to modify
   any other table (no UPDATE/DELETE/DDL; no `service_management` privileges).
3. **Identity** — `candidate_id` is a deterministic source-derived identity;
   linking to a canonical CI requires the future curation workflow with
   `matching_confidence`/`matching_basis`.
4. **Immutability** — Observation records are append-only; corrections are new
   records linked by supersedes references, never rewrites.
5. **Evidence** — Every persisted observation carries source locator, revision
   claim, SHA-256, byte count, collector version, parse boundary, timestamps
   (UTC), classification, and evidence pointer.
6. **Safety** — Collector output may never carry `approval_ref`,
   `execution_receipt`, `mutation_receipt`, `audit_event_id`,
   `closure_status`, or lifecycle states beyond `open` (schema- and
   permission-enforced).
7. **Exit condition** — Runtime collection, finding transitions,
   canonicalization, or mutation require: demonstrated observation-plane
   persistence, a reviewed transition/evidence design, separate database
   roles, and an approved follow-up ADR or amendment.

## Deferred (explicit non-decisions)

- Full canonical `services`, RTO/RPO, failure-domain, resilience-policy schema.
- Migration of the 23 `devops_platform` CIs.
- SQLite store retirement timing.
- Human approval design and agent identity semantics.
- Automated remediation or OpenTofu/Cloudflare writes.
- Closure-portal state model beyond displaying durable evidence.
- Neo4j projection synchronization design.
- Durable mutation ledger/function design for ToneRoot remediation.
- External artifact archive implementation and cryptographic signing design.
- Whether `governance`/`service_management` remain in `mydatabase` or move to
  a renamed dedicated database — revisited before canonicalization tooling.

## Long-term direction (unchanged, directional)

The source-of-truth authority matrix remains the consolidation target:
OpenTofu for edge declared state; runtime APIs for observed state; registrar
for domain expiry; app-intent manifest for app catalog; Postgres catalog for
service identity/tier/owner/RTO-RPO/lifecycle; Postgres `governance` for
change intent/gates/approvals; Temporal for execution coordination;
content-addressed object storage for evidence; Neo4j keyed to canonical IDs
for topology. Disagreements are recorded as `reconciliation_finding`s —
never silently overwritten. Change closure still requires
`authorized ∧ executed ∧ durable_mutation_recorded ∧ independently_observed`.
`CR-20260830-TONEROOT-DATA-001` remains `SYNTHETIC_FIXTURE_SIMULATION` /
`REHEARSAL_ARTIFACT` — never `EXECUTED`, `VERIFIED`, or `CLOSED`.

## Consequences

**Positive**
- A reversible, technically enforceable first write path: observation plane
  permissions make the read-only boundary durable, not just documented.
- Imported facts carry provenance instead of impersonating native data.
- Drift between OpenTofu, manifests, DNS, and Postgres becomes a first-class,
  reviewable object.
- Aligns estate practice with ADR-032's accepted evidence placement and
  ADR-028's delivery discipline.

**Costs / risks**
- `mydatabase` gains a `governance` schema — schema churn in a live database
  (additive only; no existing table changes required for v0.2).
- Candidate volume accumulates; retention and dedup policy must be operated.
- Portal and scripts must still be relabeled for CR-20260830; some existing
  "evidence" is downgraded to rehearsal status.

## Open questions for review

1. Which drift findings block deployment vs. require review vs. are
   informational?
2. Who may declare a service exists (manifest, OpenTofu, K8s discovery, human
   owner)?
3. Redaction boundary for any future open-source release of
   `aegis-control-plane`.

## References

- `aegis-control-plane/docs/reports/gap-report.md`,
  `gap-report-review-addendum.md` (2026-09-22)
- `aegis-control-plane` v0.1.0-alpha.1 — read-only reconciliation prototype
- ADR-028 (service delivery & break-glass), ADR-030 (cortex local PVs),
  ADR-031 (change impact & stakeholder governance), ADR-032 (federated
  governance & evidence placement), ADR-038 (credential inventory enrollment)

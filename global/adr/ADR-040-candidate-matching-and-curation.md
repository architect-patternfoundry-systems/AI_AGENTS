# ADR-040: Candidate-to-Canonical CI Matching, Curation, and Lifecycle Semantics

## Status

**Accepted** — proposed 2026-09-23, accepted 2026-09-24. Builds on ADR-039
(accepted): the observation plane is implemented; this ADR decides how
source-derived candidates may eventually link to canonical CIs. Linkage
requires the governed proposal/decision path defined here — `canonical_ci_id`
remains inert until that path is implemented and separately authorized.

## Context

ADR-039 created an append-only evidence plane: collectors persist
`observation_candidate` records with deterministic `candidate_id`s and open
`reconciliation_finding`s, but no component may assert that a candidate *is* a
particular canonical CI. The gap report's real data illustrates why this
restraint is warranted: `art-canvas` exists in OpenTofu, the app-intent
manifest, and the ontology registry under different keys — an automatic merge
on any single attribute would silently fabricate canonical identity.

The question this ADR answers: **what must be true before a
`candidate_id → canonical_ci_id` link may be asserted, and how are matches,
moves, and conflicts represented without rewriting evidence?**

## Proposed decisions

### 1. Proposal authority

- Match hypotheses are produced by a **`aegis_matcher` component/role**,
  distinct from `aegis_observer_writer`. Collectors never propose.
- Hypotheses are records, not mutations: `governance.match_proposal` rows
  (proposed) referencing `observation_candidate` and a candidate canonical
  target.
- Humans (or a future authorized governance workflow) record decisions in a
  separate `governance.match_decision` table. No component auto-accepts.

### 2. Match attributes

Allowed hypothesis inputs, in descending strength:

| Class | Attributes | Weight |
|---|---|---|
| Deterministic | Stable source-native IDs (`source_object_id`), canonical port + FQDN + tunnel ID tuples | High |
| Strong | FQDN alone; OpenTofu resource address; K8s namespace/workload coordinates | Medium |
| Weak | Service name, port alone, display name | Suggestive only |
| Contextual | Owner team, lifecycle state, environment | Tiebreaker only |

Single weak attributes never produce a proposal — they annotate ambiguity.

### 3. Confidence representation

| State | Meaning |
|---|---|
| `deterministic` | Source-native stable key matches exactly |
| `high_confidence` | Multiple independent strong attributes agree |
| `ambiguous` | Multiple plausible targets or only weak attributes |
| `conflict` | Strong attributes contradict (e.g., FQDN matches but tunnel ID differs) |

Confidence is recorded with `matching_basis` — a structured record of the
attribute/value/provenance tuples used — never as a bare score.

### 4. Acceptance and decision outcomes

A `match_decision` records one of five outcomes:

| Decision outcome | Meaning |
|---|---|
| `accepted` | Candidate is linked to the canonical CI |
| `rejected` | Candidate is explicitly **not** that canonical CI under the stated evidence and basis |
| `deferred` | Not decidable yet — insufficient evidence; revisit after a stated condition or date |
| `superseded` | A later decision replaces the prior decision |
| `withdrawn` | Proposal was invalidated before adjudication |

`rejected` and `deferred` are distinct: rejection asserts "not this pair
under this evidence"; deferral asserts "not decidable yet." A `deferred`
decision **must** carry a revisit condition or date. A `rejected` decision
may carry an optional review expiry where the underlying evidence is
expected to change; expiry duration should scale with basis strength and
evidence volatility — a rejection grounded in deterministic identifiers is
expected to persist longer than one grounded in weak attributes.

Every decision requires: `candidate_id`, `canonical_ci_id`,
`matching_basis` (a structured record of attribute/value/provenance — never
a prose score explanation alone) and confidence classification, `actor`
(a **resolvable** adjudicator identity — account or subject ID, not
free-form text), `recorded_at`, `decision`, `reason_code`, `evidence_ref`,
and `matching_policy_version` — an immutable identifier (content hash or
Git revision) of the policy/configuration used to generate the proposal.

- Only an `accepted` decision may populate `canonical_ci_id` — and even then,
  via a new append-only linkage record, not by editing history.
- All outcomes, including `withdrawn`, are append-only events: a withdrawn
  proposal preserves its reason and is never deleted.

**Negative-match memory.** A `rejected` decision is a durable
"do not re-propose under the same basis" control. The matcher must filter a
candidate/CI pair from scoring/presentation while the candidate lineage,
canonical CI identity, matching-policy version, and evidence basis are
materially equivalent to the rejected decision.

A previously rejected pair may be re-proposed only when at least one of the
following has changed relative to the rejected decision. Each is a named
`material_change_type`:

1. `candidate_lineage_or_source_snapshot_changed` — candidate lineage or
   source snapshot identity;
2. `canonical_ci_changed` — canonical CI identity, lifecycle, or
   identifying attributes;
3. `matching_policy_version_changed` — matching policy/rule version;
4. `strong_identifier_available` — a deterministic or strong identifier
   becomes available;
5. `evidence_corrected_superseded_or_expanded` — referenced evidence is
   corrected, superseded, or materially expanded;
6. `basis_canonicalization_version_changed` — the canonicalizer version
   changed (serialization rules are governance-controlled).

A re-proposal **must** include `supersedes_decision_id`,
`material_change_type`, `material_change_evidence_ref`, the new
`matching_basis`, and the new `matching_policy_version` — a
machine-checkable escape hatch, not reviewer interpretation. Rejection is a
durable outcome, never a deletion.

**Deterministic basis equivalence.** Suppression cannot rely on text
comparison. `matching_basis` shall be canonically serialized into a
`basis_fingerprint`:

```text
basis_fingerprint = SHA-256(canonicalize(
  candidate_id,
  canonical_ci_id,
  ordered(attribute, normalized_value, provenance_ref,
          observed_at_or_snapshot),
  matching_policy_version
))
```

The conceptual suppression key is `(candidate_lineage_id, canonical_ci_id,
matching_policy_version, basis_fingerprint)`. Tuple ordering, prose,
inconsistent normalization, or irrelevant added evidence must not alter
equivalence — a re-proposal is permitted only when an enumerated
`material_change_type` corresponds to a changed, evidence-backed component
of that key. Suppression comparisons apply only to fingerprints computed
under the same `basis_canonicalization_version`; fingerprints across
canonicalizer versions are incomparable by definition.

**Canonicalization contract.** `canonicalize()` must produce identical
bytes for semantically identical input across matcher versions and
implementation languages:

- Attribute names: fixed schema identifiers — never display labels.
- Value normalization: defined per attribute type — UUIDs lowercase; MACs
  lowercase colon notation; hostnames per a stated normalization policy;
  whitespace handling, Unicode normalization form, and null representation
  are all explicit.
- Provenance references: immutable content digest, source snapshot ID, or
  versioned URI — never a mutable "latest" path.
- Timestamps: RFC 3339 UTC at stated precision, or the immutable source
  snapshot identity in place of per-observation timestamps.
- Tuple order: lexicographic sort over fixed fields with a stated
  deterministic tie-breaker.
- Relevance: only attributes flagged `matching_relevant: true` enter the
  fingerprint; additional irrelevant evidence changes nothing.
- Absence: `null`, missing, empty string, unknown, and redacted serialize
  distinctly where their semantics differ.
- Versioning: every proposal and decision records an immutable
  `basis_canonicalization_version`; changing it changes fingerprints and is
  a governed material change
  (`basis_canonicalization_version_changed`), never an accidental global
  reopening of rejected pairs.

The fingerprint is an index and equivalence accelerator, not permission to
conflate records: where fingerprints collide or cannot be computed, the
canonical serialized payloads (or the versioned structured basis) are
compared directly. A proposal whose basis cannot be canonically serialized
is rejected before scoring or presentation.

### 5. Source movement and identity history

- File moves, renames, and coordinate changes produce a **new
  `candidate_id`** linked by `candidate_supersedes_candidate_id`; the old
  record is never edited.
- A moved source that already links to a canonical CI generates a proposal
  to *carry* the link to the superseding candidate — decided, never
  automatic. An accepted association does **not** transfer on a source move;
  the new candidate is unlinked until adjudicated.
- A changed `candidate_id` alone is never evidence of a match. Because
  `candidate_id` participates in the fingerprint, a move changes the
  fingerprint — but this only makes the superseding candidate *eligible*
  for re-adjudication under `candidate_lineage_or_source_snapshot_changed`.
  The new proposal must still provide a newly computed `matching_basis` and
  evidence; the material-change type is the auditable reason, not the
  justification.
- Splits/merges/decommissions are represented as proposals with explicit
  `source_change_kind`; the canonical CI lifecycle is owned by
  `service_management`, not by source observations.

### 6. Conflict behavior

- Field-level authority is per-fact-class (ADR-039 authority matrix): a
  canonical CI's `owner_team` is not overridden by a manifest, but a declared
  `canonical_port` conflict raises a `reconciliation_finding`.
- Contradictions are **surfaced as findings**, never resolved by silent
  overwrite or last-writer-wins.

### 7. Auditability

- Proposals and decisions are append-only rows; reversal is a new decision
  superseding the prior one (`supersedes_decision_id`), never an update.
- The observation tables remain untouched by matching: linkage lives in its
  own records.

## Deferred

- `canonical_ci_id` FK creation and target table finalization.
- Automatic linkage thresholds (if any are ever permitted).
- Bulk reconciliation of the existing 23 `devops_platform` + 4
  `service_management` CIs.
- Matcher implementation, scheduling, and review UI.

## Acceptance conditions

1. Match proposals shall be attributable, evidence-bearing, and append-only.
2. No component shall auto-populate `canonical_ci_id`.
3. Weak-attribute-only hypotheses shall not produce proposals.
4. Contradictory strong attributes shall produce `conflict` findings.
5. All match decisions shall be reversible only by supersession.
6. Source moves shall preserve full candidate lineage.
7. A `rejected` candidate/CI pair shall not be re-proposed while lineage,
   canonical CI, policy version, and evidence basis are materially
   equivalent; re-proposal shall carry `supersedes_decision_id`,
   `material_change_type`, `material_change_evidence_ref`, and the new
   `matching_basis`/`matching_policy_version`.
8. `deferred` decisions shall carry a revisit condition or date; `actor`
   and `matching_policy_version` shall be resolvable, immutable identifiers
   on every decision.
9. `matching_basis` shall be canonically serialized into a deterministic
   `basis_fingerprint`; equivalence shall be decided by that fingerprint and
   the suppression key, never by text comparison.
10. Canonicalization shall be specified deterministically enough for
    independent implementations to produce identical fingerprints; only
    `matching_relevant` attributes participate; absent, unknown, and
    redacted values serialize distinctly.
11. `basis_fingerprint` is an equivalence accelerator: differing canonical
    payloads shall never be conflated on collision, and unserializable
    bases shall be rejected before scoring.
12. A changed `candidate_id` alone shall confer only eligibility for
    re-adjudication under an explicit `material_change_type` — never an
    implicit match or a carried-over accepted link.

## References

- ADR-039 (observation plane, identity layers, `canonical_ci_id` constraint)
- ADR-032 (evidence placement), ADR-031 (change impact/stakeholder governance)
- `aegis-control-plane` contracts: `candidate-record/v1`,
  `finding-transition/v1`

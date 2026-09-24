# ADR-041: Canonical Linkage Materialization and Effective-Identity Resolution

## Status

**Proposed** — 2026-09-24. Builds on ADR-039 (observation plane, accepted)
and ADR-040 (match proposals/decisions, accepted). ADR-040 defined how a
candidate↔CI hypothesis is proposed and adjudicated; it deliberately did
not define what an `accepted` decision *materializes*. This ADR answers
that question. Until accepted, `observation_candidate.canonical_ci_id`
remains an inert nullable external reference and no linkage exists.

## Context

The evidence chain now ends at an append-only `match_decision`. An
`accepted` decision is a governance fact — "adjudicator X accepted that
candidate Y is canonical CI Z under basis B" — but the system has no
defined answer to the operational question that follows: **what is the
current effective linkage, who may materialize it, and how is it revoked
without rewriting history?**

The failure modes if this is left implicit:

- a mutable `canonical_ci_id` column quietly conflates *what the collector
  observed* with *what governance later concluded*;
- competing accepted decisions produce an arbitrary winner;
- a revoked or superseded link leaves stale assertions in place because
  there is no deactivation event;
- a projection defect or CI merge/split cannot be repaired without
  rewriting evidence.

## Proposed decisions

### 1. Acceptance materializes an event, not a mutation

An `accepted` match decision authorizes an append-only
`candidate_ci_link` event. It does **not** update
`observation_candidate.canonical_ci_id` and never rewrites collected
evidence:

```text
match_decision (accepted, append-only)
  └─ candidate_ci_link event (append-only authorization record)
      └─ effective_candidate_ci_link (rebuildable projection)
```

The existing nullable `canonical_ci_id` column remains unused. It is
deprecated or repurposed only by a future migration after this ADR is
accepted — never populated as a side effect of decisions.

### 2. Effective identity rule

The effective link for a candidate is deterministic:

1. Consider only `candidate_ci_link` events of type `activated` whose
   authorizing decision is **current** (not superseded by a later
   decision).
2. If exactly one current activation exists for the candidate lineage →
   that is the effective link.
3. If zero → the candidate is unlinked.
4. If two or more mutually incompatible current activations exist →
   **conflict**: no effective link is projected and a
   `reconciliation_finding` is raised. Fail-closed, never last-writer-wins.

Ordering is by explicit supersession chain first, `recorded_at` as
tie-breaker — identical to decision supersession semantics (ADR-040).

### 3. Link lifecycle

- Links are deactivated by new append-only link events (`superseded`,
  `revoked`), never by UPDATE/DELETE.
- A source move produces a new `candidate_id` (ADR-040): the link does
  not carry over; the superseding candidate is unlinked until its own
  proposal is accepted.
- Canonical CI merges/splits are `service_management` lifecycle events;
  affected links are revoked by explicit link events citing the CI
  lifecycle record — the projection then recomputes.
- Decommissioning a CI revokes its links via events; historical
  activations remain for audit.

### 4. Authority separation

- `aegis_match_adjudicator` records decisions (existing role, ADR-040).
- Link events are written by a distinct `aegis_linker` role whose insert
  is gated on a current accepted decision — materialization is a
  constrained projection action, not a second human approval, but it is
  a **separate privilege** so a compromised adjudicator path cannot also
  mint linkage.
- No role may write both decisions and links.

### 5. Projection versus evidence

`effective_candidate_ci_link` is a rebuildable projection (view or
maintained table) derived solely from append-only link events and
decisions. It may be dropped and recomputed after policy changes, data
repair, CI merge/split, or projection defects — without touching
evidence. Consumers read the projection for current truth and the event
tables for history.

### 6. Conflict handling

- Two current accepted decisions mapping one candidate lineage to
  different CIs → conflict finding; no effective link.
- One canonical CI claimed by mutually incompatible candidates → conflict
  finding; both links remain recorded but neither is projected as
  effective until adjudication resolves the conflict.
- Conflicts are findings with evidence references — never silent
  resolution.

## Deferred

- `candidate_ci_link` table shape and the projection's concrete form
  (view vs. maintained table).
- Deprecation/migration of the inert `canonical_ci_id` column.
- Who operates `aegis_linker` (workflow automation vs. operator step).
- Link-event evidence requirements for CI merge/split revocations.
- Retroactive linkage of existing candidates once canonical CIs exist.

## Acceptance conditions

1. Linkage shall be materialized only as append-only events authorized by
   a current `accepted` decision — never by mutating observation rows.
2. `observation_candidate.canonical_ci_id` shall remain unpopulated;
   effective linkage resolves through the projection.
3. The effective-identity rule shall be deterministic and fail-closed on
   conflict.
4. Deactivation shall be a new event; history shall never be rewritten.
5. The projection shall be rebuildable from events alone.
6. No single role shall be able to both adjudicate and materialize links.
7. Source moves shall unlink the superseding candidate until separately
   adjudicated and accepted.

## References

- ADR-040 (match proposals, decision outcomes, suppression, lineage)
- ADR-039 (observation plane; `canonical_ci_id` as inert external ref)
- ADR-032 (evidence placement; append-only ledgers)
- `aegis-control-plane` migration 0002 (`match_proposal`, `match_decision`)

# ADR-044: Boundary Error Contracts — Structured Facts over Producer Retry Policy

* **Status**: Proposed
* **Date**: 2026-11-19
* **Decides**: How service boundaries represent failure — what producers emit, what consumers decide, and how the reason vocabulary evolves
* **Related**: ADR-027 (Standardize ToneRoot Logging), ADR-031 (Change Impact and Stakeholder Governance), ADR-043 (Verified Credential Resolution)

---

## 1. Context & Problem Statement

Two incidents in November 2026 exposed the same contract gap from opposite
directions:

- **GPU-nanny probe failure (`engine_not_ready`)**: the nanny's engine
  readiness probe used `requests.get()` against `f5-tts:9998` — a raw TCP
  protocol socket that drops HTTP by design. Deployments went available,
  the probe could never pass, and `engine_state` pinned at `NANNY_READY`
  forever. Every leased F5 workflow then burned a 420 s readiness deadline
  and failed `engine_not_ready` — an opaque reason that gave consumers no
  way to distinguish "queue full, retry" from "probe mechanism broken,
  retry is pointless." The bug also shows the amplification risk: a wrong
  classifier emits its misjudgment deterministically, and the more
  authoritative the error surface looks, the longer the misclassification
  hides.
- **ToneRoot Suno download limits**: upstream policy changes made clips
  undownloadable via several distinct mechanisms (sentinel URL, disable
  flags, conversion denial/timeout). An unstructured `"Error"` surface
  collapsed these into one outcome — consumers could not tell a
  next-billing-cycle retry from a policy decision that will never change.

The general problem: **a producer-side retry hint (`retryable: bool`,
"try later") collapses facts the producer knows into a policy decision it
does not own.** Quota exhaustion is retryable next billing cycle; rate
limiting is retryable in minutes; a dead endpoint is never retryable —
one boolean cannot hold all three, and the producer does not know what
each consumer is willing to spend.

## 2. Decision

Service boundaries carry failure as **structured facts**, not producer
retry policy.

1. **Stable, namespaced reason vocabulary.** Reasons are machine-readable
   constants owned by the producer (e.g. `BR_DOWNLOAD_DISABLED`,
   `conversion_denied`, `probe_never_verified`), namespaced by domain
   (`nanny.*`, `suno.*` for extension values). They are a public contract:
   treated like API fields, changed deliberately, versioned when they
   break consumers.
2. **Fact fields, not a `retryable` flag.** Producers emit what they
   uniquely know: `reason`, `retry_hint` (a vocabulary of *when/how* —
   `next_billing_cycle`, `rate_limit_cooldown`, `check_plan`, `next_run`,
   `manual_recheck`), `blocked_until` / `retry_after_ms`, `deadline_ms`,
   last probe status, identifiers. The **consumer maps facts to its own
   retry/degrade/escalate policy** — a batch job and a UI click have
   different answers to the same fact set. A `retryable` boolean is the
   weakest possible contract; omit it or treat it as advisory only.
3. **Closed-by-default fallback for unknown reasons.** The enum will
   grow. Consumers MUST treat an unrecognized reason as
   non-retryable/conservative (the same err-closed rule already used for
   resource admission: unknown job type counts as audio, unknown spend
   policy becomes conservative). This must be documented, not emergent.
4. **Correct state machine before typed exits.** Classification precedes
   typing: a typed error amplifies whatever the classifier believes.
   Before publishing a reason value, the producer must verify the
   underlying transition is real (probe contract correct, state machine
   can reach the terminal state). Typed errors compress the forensic
   loop; they do not prevent misclassification — they make it legible
   faster, which is the actual benefit.
5. **Telemetry is not the API.** Full forensic detail (probe history,
   per-item breakdowns, intermediate states) goes to logs/events and may
   churn. The consumer contract is deliberately small and slow-moving
   (e.g. exact counts as scalars, capped detail lists).
6. **Right-size the formalization.** Internal services with a handful of
   consumers implement the middle tier: stable reason constants + fact
   fields + typed internal exceptions. A versioned cross-service error
   protocol (RFC-9457-style) is justified only when external consumers
   exist or the surface must be spoken by independently evolving
   services.

## 3. Consequences

- Consumers stop inferring retry policy from log strings; producers stop
  guessing consumer tolerance.
- New failure modes add namespaced reasons without breaking consumers
  that honor the closed-by-default rule.
- Producers inherit an obligation: reason values must be backed by a
  correct, verifiable state transition — a fabricated or speculative
  reason is worse than none.
- Internal exception types (e.g. `LeaseWaitError` carrying `retryable`
  semantics) remain free to be richer than the boundary contract;
  boundary serialization applies this ADR's subset.
- Does not mandate transport shape — applies equally to exception
  types, task-result dicts, event payloads, and HTTP error bodies.

## 4. Alternatives Considered

- **Producer-side `retryable` flag / enum** — collapses time-dependent
  and consumer-dependent facts into a producer guess; rejected as the
  primary contract (acceptable only as an optional advisory field
  alongside facts).
- **Full versioned error protocol (RFC 9457 + details extension)** —
  correct shape, premature scope: with ~3 internal tenants we control,
  the versioning/migration cost outweighs the benefit until external
  consumers exist.
- **Free-form reason strings** — strings drift, get string-matched by
  consumers, and break silently; rejected — constants with a documented
  fallback are nearly free.

## 5. Evidence & References

- ToneRoot downloader: `BR_*` reason taxonomy, `download_blocks` with
  `blocked_until`, `download_summary.unavailable_details` (capped at 50)
  — application repo `feat/suno-download-quota-handling`.
- GPU-nanny: `9c07ff4a` TCP-connect probe for socket engines; the
  `NANNY_READY`-forever → `engine_not_ready` incident motivating reason
  granularity; `SOCKET_ENDPOINT_SERVICES` classification list.
- CTS `LeaseWaitError` typed exception (storyloom#51) — typed internal
  surface carrying structured retry context.
- GitOps census misses (#377→#384, #388) — a parallel instance of the
  same "facts about consumers must be explicit" principle, codified in
  `global/operations.md` (consumer-marker convention).

# ADR-026: Unified Log Intelligence Platform for Streaming and Batch Analysis

## Status
Proposed

## Date
2026-07-19

## Author
Perplexity AI

## Deciders
Committee review

## Related docs
Reference architecture for combined log stream and batch analysis

## Scope
Kubernetes application logs, platform logs, and operator-facing tuning guidance

## Context and Problem Statement

A single operator managing a complex Kubernetes-based stack needs a way to stay ahead of log-driven issues across multiple applications. Today, live logs are useful for immediate awareness, but they do not provide durable clustering, historical pattern discovery, or a systematic way to produce tuning checklists. The desired outcome is a platform that continuously analyzes log streams, reprocesses historical logs in batch, and converts both into concise operational guidance.

The system must support multiple applications and recurring patterns such as short-lived connection churn, benign startup errors, noisy probes, and emerging failure modes. It must preserve raw logs for replay and backfill, because cluster definitions will evolve over time. The architecture should therefore balance freshness, correctness, explainability, and operational simplicity.

## Decision

We will implement a dual-path log intelligence platform with a shared durable log source, a streaming clustering path, a batch clustering path, and a higher-level analytics layer that produces operator-facing summaries and tuning checklists.

The stream path will use **Drain3** for live template mining and near-real-time clustering. The batch path will use **SLCT** for periodic historical discovery of recurring and rare patterns. A top-level intelligence layer will use **LogAI** to summarize clusters, detect anomalies, and produce normalized issue records. Raw logs will remain the source of truth, and all derived results will be reproducible from history.

## Decision Drivers

- Need for near-real-time detection of log patterns
- Need for historical correctness and backfill
- Need to support multiple apps with mixed log formats
- Need to generate operator-friendly tuning checklists rather than raw noise
- Need to preserve logs for replay and iterative improvement
- Need to keep the system understandable and maintainable for a solo operator

## Considered Options

1. **Drain3 only**
2. **SLCT only**
3. **LogAI only**
4. **Drain3 + SLCT + LogAI with shared durable log storage**
5. **Kappa-style single stream with replay-only batch recomputation**

## Decision Outcome

Chosen option: **Drain3 + SLCT + LogAI with shared durable log storage**, because it best satisfies freshness, correctness, and explainability simultaneously while allowing the operator to recover from drift, refine patterns, and generate actionable checklists.

### Pros and expected benefits

- Live clustering is available immediately through Drain3
- Historical pattern discovery is improved by SLCT batch sweeps
- Operator summaries and anomaly explanations are produced by LogAI
- Raw logs can be replayed to rebuild derived views when rules change
- The platform can support multiple applications without custom parsers for every service

### Cons and potential risks

- The architecture is more complex than a single-tool approach
- Separate stream and batch outputs can disagree temporarily
- Rules and cluster mappings will require periodic human review
- There is risk of false positives if cluster thresholds are too permissive
- Additional storage is required to preserve the raw log history

## Consequences

### Positive consequences

The operator gains a continuously improving log analysis loop that can detect current noise, confirm historical trends, and turn both into explicit actions. The system can surface likely tuning issues earlier, such as short-lived connection churn, repeated startup warnings, or pattern drift across services. Because the serving layer is derived, it can be rebuilt and refined without losing the original data.

### Negative consequences

The platform introduces a second analytical system alongside the existing logging stack, so it must be governed carefully. The committee should expect some initial tuning work to calibrate pattern thresholds, reduce false positives, and reconcile stream-versus-batch differences. The system will also require a lightweight taxonomy of issue types so the checklist engine can produce consistent output.

## Implementation Notes

- Store all raw logs in a durable location before any clustering or summarization
- Run Drain3 continuously on new log events to produce live template IDs
- Run SLCT on scheduled historical windows to discover missed patterns and rare signatures
- Feed both outputs into LogAI for summary generation and anomaly scoring
- Maintain a canonical issue registry that tracks pattern identity, status, severity, and checklist items
- Keep a feedback loop so operator review updates the catalog over time

## Acceptance Criteria

The ADR may be moved from Proposed to Accepted when the committee agrees that:
- The three-layer design is appropriate for the intended operator workflow
- Raw logs will be retained long enough for replay and backfill
- The platform can produce useful per-app tuning checklists
- The initial implementation scope is manageable
- The review process for new patterns and checklist rules is defined

## Follow-up Actions

- Define the raw log retention policy
- Select the durable log store or broker
- Define the canonical issue schema
- Decide the first set of applications to onboard
- Write the implementation ADRs for ingestion, clustering, and reporting

## Links

- Decision log entry for committee tracking
- ADR template reference
# ADR-027: ToneRoot Logging Standardization

## Status
Accepted

## Context
ToneRoot local development and cluster operations output a high volume of interleaved, flat text logs. This includes Tilt orchestration, Docker builds, Flux suspension, KEDA annotations, and verbose frontend lifecycle noise. The flat structure makes it difficult to detect true failures, observe control-plane state mutations, and filter logs by role or lifecycle phase.

## Decision
ToneRoot standardizes logging around a versioned structured event envelope with explicit lifecycle phases, command/resource classification, noise mitigation, and security constraints.

1. **Canonical Schema Envelope**  
   Every event must include `schema_version`, `ts`, `source`, `phase`, `action`, `result`, `severity`, `message`, and `correlation_id`.
   - The initial schema version is defined as `v1`.

2. **Schema Versioning & Compatibility**
   - The schema version (`schema_version`) must be included in every structured event.
   - Minor changes (e.g. adding new optional fields) must be additive.
   - Breaking changes (e.g. renaming or removing required fields) require a new major schema version and a migration plan.
   - Accepted ADRs are append-only; if the logging contract changes materially, a follow-up ADR must be written that supersedes this one.

3. **Phase Separation**  
   Events must be classified into one of: `startup`, `suspend`, `build`, `push`, `deploy`, `runtime`, `teardown`.

4. **Command and Resource Classification**  
   Shell and kubectl execution must emit structured metadata including `resource_kind`, `resource_name`, `namespace`, `command`, and `exit_code` where applicable. Optional resource absences must be classified explicitly as `expected_missing` when benign.

5. **Noise Mitigation**  
   Repetitive runtime logs must be deduplicated or aggregated where they do not add new diagnostic value.

6. **Security and Privacy Constraints**  
   - Logs must not include secrets, tokens, raw credentials, session cookies, or access credentials.
   - Personally Identifiable Information (PII) should be avoided by default.
   - Sensitive fields must be classified and scrubbed/redacted at emission time.

7. **Explicit Severity Semantics**
   - `debug`: Developer-only diagnostics and high-volume trace information.
   - `info`: Expected lifecycle transitions, successful operations, and benign events (including `expected_missing` only when the absence is explicitly classified as benign).
   - `warn`: Unexpected but non-fatal conditions, transient failures, or degraded performance states.
   - `error`: Failed operations or unrecoverable conditions requiring attention.

8. **Emission and Enforcement Model**
   - Emitters should use shared logging wrappers to ensure consistent formatting.
   - CI/CD pipelines will validate schema conformance for all code paths. Conformance validation is the preferred enforcement gateway.
   - Runtime collectors may enrich logs but must not be the sole source of truth for required fields.

9. **Reserved Fields for Observability Integration**
   The following fields are reserved for future correlation and tracing:
   - `trace_id`, `span_id`, `service`, `manifest`, `pod`, `container`, `route`, `status_code`
   - These fields are optional in `v1` but expected to be populated where instrumentation exists (e.g. request routing or distributed service boundaries). The absence of these optional fields must not fail validation in `v1`.

The concrete specification, taxonomy details, and implementation checklists are stored as repository-local records under ToneRoot's `docs/observability/`.

## Consequences
- Emitters and tools in ToneRoot must conform to the structured logging contract.
- Consumers may index structured logs into relational or vector-backed stores for retrieval and governance queries.
- Schema versioning and validation introduce some implementation overhead.
- Log quality becomes testable, which improves long-term maintainability.
- Security review becomes easier because the log contract defines what must never be emitted.

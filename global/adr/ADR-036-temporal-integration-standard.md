# ADR-036: Temporal Integration Standard — Cross-App Durable Orchestration

* **Status**: Accepted (Platform Integration Standard)
* **Date**: 2026-09-05
* **Decides**: How applications participate in Temporal-based durable orchestration, including workflow contracts, task-queue topology, identity rules, artifact publication, and ownership boundaries
* **Amends**: ADR-020 (GPU Resource Arbitration), ADR-028 (Service Delivery and Break-Glass Recovery)
* **Related**: ADR-035 (CTS Temporal Pilot — Ollama Lease Wiring), ADR-032 (Federated Governance and Evidence Placement)

---

## 1. Context and Problem Statement

### 1.1 Current state

The platform has multiple applications that perform durable, multi-step work crossing system boundaries:

- **CTS** (Attunement Weaver): transcribes audio via Whisper, enriches via Ollama, stores transcripts. Has a Temporal pilot (`cts-temporal-pilot`) but primarily uses an in-process queue worker with a database-backed state machine (`pending → leasing → processing → terminal`).
- **Casting Signal**: generates multilingual TTS corpus batches via AllTalk. Has a Temporal submission script (`submit_japji_temporal_batch.py`) but the UI is not wired to it — it always calls a direct local script.
- **Nexus**: audio catalog, conversion, and playback-URL registration. Currently disabled (`NEXUS_INGEST_ENABLED=false`).
- **ToneRoot**: media storage and delivery with S3-backed playback. Works but is not integrated with the other apps' orchestration.

Each app has independently invented retry, state-management, lease-acquisition, and artifact-storage patterns. This creates:

- Duplicated retry/backoff logic that is non-durable across restarts.
- Inconsistent artifact storage and catalog registration.
- No cross-app correlation or audit trail for composite operations.
- No standard way to observe or govern multi-app workflows from a single place.
- Race conditions and stale-lease accumulation (as observed in CTS and GPU Nanny).

### 1.2 Goal

Establish Temporal as a **shared control plane for durable orchestration** without turning it into a centrally owned monolith. Each app owns its domain; Temporal owns the durable process contract.

---

## 2. Decision

### 2.1 Core model

Four layers with distinct responsibilities:

```
App UI / API / Event source
        │
        │ Start, Signal, Query, Cancel
        ▼
Temporal workflow contract
        │
        ├── orchestration and durable state
        ├── retry and timeout policy
        ├── human approval / wait states
        ├── cross-app dependency ordering
        └── compensation / cleanup decisions
        │
        ▼
Domain activity adapters
        │
        ├── CTS / transcription + enrichment
        ├── casting-signal / corpus and TTS generation
        ├── Nexus catalog / conversion / publication
        ├── GPU Nanny / capacity reservation
        └── S3-compatible storage and delivery
        ▼
Domain systems and infrastructure
```

### 2.2 Ownership boundaries

**Temporal owns:**
- Workflow execution identity and lifecycle.
- Ordered orchestration steps.
- Retries, timeouts, backoff, and cancellation propagation.
- Durable waiting: human approval, external callback, resource availability.
- Normalized high-level outcome: completed, failed, canceled, awaiting approval, degraded.
- Cross-service correlation IDs and audit trail.

**Each application owns:**
- Its domain database and canonical entities.
- Its user-facing UI and authorization rules.
- Its actual service integrations, models, API calls, and domain validation.
- Its data artifacts: source audio, WAV outputs, manifests, catalog records.
- Its internal processing details.

Temporal is not a replacement for application databases. It stores orchestration state and durable references, not business objects or large payloads.

### 2.3 What qualifies as a Temporal workflow

| Situation | Best fit |
|---|---|
| Quick synchronous CRUD under a request deadline | Normal app API/database transaction |
| One service needs a short background task | Local background worker or simple activity |
| Work takes minutes/hours, retries, or survives pod failure | Temporal workflow |
| Work spans several systems or has compensations | Temporal parent workflow with activities/child workflows |
| Requires a human decision | Workflow waiting for a signal |
| Is GPU-limited or hardware-specific | Dedicated activity task queue plus lease/capacity adapter |
| Produces large files | Object storage plus artifact manifest; Temporal stores references |
| Needs cross-app status in UI | Local projection fed by workflow events/status |
| Must invoke an independently owned service workflow | Child workflow (same context) or Nexus operation (cross-domain) |

---

## 3. Workflow Integration Contract

### 3.1 Standard input envelope

Every workflow start carries a consistent envelope containing references and stable identifiers — not large payloads:

```json
{
  "request_id": "req_01J...",
  "workflow_id": "casting-corpus:batch_01J...",
  "workflow_type": "media.corpus-batch.v1",
  "source_app": "casting-signal",
  "tenant_id": "patternfoundry",
  "project_id": "japji-matrix",
  "correlation_id": "corr_01J...",
  "causation_id": "event_01J...",
  "idempotency_key": "casting-corpus:batch_01J...",
  "requested_by": {
    "subject_id": "user_or_service_id",
    "actor_type": "user"
  },
  "priority": "batch",
  "governance": {
    "approval_required": true,
    "dry_run": false,
    "force_regenerate": false
  },
  "input_ref": {
    "kind": "s3-json-manifest",
    "uri": "s3://bucket/manifests/batch_01J.json",
    "checksum": "sha256:..."
  }
}
```

Heavyweight inputs and outputs are stored in S3-compatible object storage. Temporal retains orchestration state and durable references only.

### 3.2 Standard result envelope

Every workflow finishes with a portable result:

```json
{
  "workflow_id": "casting-corpus:batch_01J...",
  "run_id": "temporal-run-id",
  "status": "completed_with_warnings",
  "summary": {
    "requested_items": 280,
    "generated_items": 276,
    "skipped_items": 2,
    "failed_items": 2
  },
  "artifacts": [
    {
      "kind": "audio-manifest",
      "uri": "s3://bucket/corpus/batch_01J/manifest.json",
      "checksum": "sha256:..."
    }
  ],
  "catalog_refs": [
    {
      "system": "nexus",
      "entity_type": "audio-corpus-batch",
      "entity_id": "nexus_..."
    }
  ],
  "warnings": [
    {
      "code": "VOICE_REFERENCE_MISSING",
      "scope": "locale:ar"
    }
  ],
  "correlation_id": "corr_01J..."
}
```

### 3.3 Workflow ID convention

```
<domain>:<operation>:<business-id>
```

Examples:
```
cts:ingest:job_20260903211130_5_q
casting:corpus-batch:batch_01JABC
nexus:publish:asset_01JXYZ
media:transcode:artifact_sha256_...
```

### 3.4 Idempotency rules

| Operation | Workflow ID behavior |
|---|---|
| User starts a new corpus batch | Stable ID per submitted batch |
| User retries same failed batch | Signal/retry existing workflow or create `:attempt:N` |
| Force regenerate | New immutable generation ID; link to prior batch |
| Publish an artifact | Stable ID per artifact version |
| Manual approval | Signal the existing workflow; do not start another |
| Scheduled maintenance | Stable schedule-generated ID with intended execution period |

---

## 4. Task-Queue Topology

Separate task queues provide deployment and resource isolation. GPU work should not be starved by metadata conversion, and batch corpus generation should not crowd out interactive transcription.

| Layer | Namespace | Task queue | Worker | Purpose |
|---|---|---|---|---|
| Shared platform | `patternfoundry-dev` | N/A | Temporal cluster | Orchestration engine |
| CTS workflow control | `patternfoundry-dev` | `cts-workflows` | CTS worker | Ingestion/transcription orchestration |
| CTS GPU activity | `patternfoundry-dev` | `media-gpu` | GPU-capable CTS worker | Whisper transcription execution |
| Casting Signal orchestration | `patternfoundry-dev` | `casting-workflows` | Casting workflow worker | Corpus batch orchestration |
| TTS generation | `patternfoundry-dev` | `tts-gpu` | TTS/AllTalk worker | TTS synthesis execution |
| Nexus conversion/catalog | `patternfoundry-dev` | `nexus-publication` | Nexus worker | Catalog registration and playback URL generation |
| Storage/validation | `patternfoundry-dev` | `media-io` | I/O worker | S3 upload, validation, manifest writing |

Start with one namespace per environment. Separate namespaces become valuable when apps or teams need distinct credentials, retention, quotas, or on-call boundaries.

---

## 5. Standard Workflow Portfolio

### 5.1 Corpus batch workflow (Casting Signal)

```
CorpusBatchWorkflow v1
  ├── ValidateCorpusRequest
  ├── ValidateReferenceAudio
  ├── AwaitApproval (if policy requires)
  ├── ReserveGpuCapacity
  ├── GenerateLocaleBatches
  │     └── GenerateSegment child workflow × locale / voice / matrix node
  ├── ValidateAudioArtifacts
  ├── ConvertAndNormalizeForPlayback
  ├── PersistToObjectStorage
  ├── RegisterNexusCatalogEntries
  ├── PublishPlaybackManifest
  └── ReleaseGpuCapacity
```

Partition by locale (one child workflow per locale) with batched activities per matrix segment. This gives per-locale isolation, resumability, and a concise UI status model.

### 5.2 CTS ingestion workflow

```
MediaIngestionWorkflow v1
  ├── ValidateSource
  ├── AcquireWhisperLease
  ├── Transcribe
  ├── OptionalEnrichment
  ├── StoreTranscript
  ├── RegisterNexusArtifacts
  └── ReleaseLeases
```

The workflow replaces application-local polling as the durable owner of retries and waiting. CTS remains the executor of transcription activities; it does not surrender ownership of its job model.

### 5.3 Nexus publication workflow

```
NexusPublicationWorkflow v1
  ├── ValidateArtifactManifest
  ├── ConvertForPlayerCompatibility
  ├── RegisterCatalogRecord
  ├── GenerateSignedPlaybackReferences
  ├── UpdateGraph / mappings
  └── PublishCompletionEvent
```

This makes "stored like ToneRoot, with Nexus conversion/catalog and S3 URL playback" an explicit, independently observable contract.

### 5.4 Human-governed workflow

```
GovernedBatchWorkflow v1
  ├── Validate
  ├── EstimateCost / Capacity
  ├── AwaitHumanApproval
  ├── Execute child workflow
  └── Publish audit outcome
```

Use Temporal signals for approval decisions rather than keeping HTTP requests or web sessions open.

---

## 6. Standard App Adapter Pattern

Each app integrates through three small components:

### 6.1 Workflow client adapter

```python
class OrchestrationClient:
    async def start(
        self,
        workflow_type: str,
        workflow_id: str,
        request: WorkflowRequest,
    ) -> WorkflowHandle: ...

    async def signal(
        self,
        workflow_id: str,
        name: str,
        payload: dict,
    ) -> None: ...

    async def status(
        self,
        workflow_id: str,
    ) -> WorkflowStatus: ...
```

Every application uses this adapter rather than inventing its own Temporal client behavior, retry policy, headers, tracing, or workflow naming scheme.

### 6.2 Activity adapter

Each domain service exposes narrowly scoped, idempotent operations:

```python
generate_wav(request) -> AudioArtifact
validate_audio(artifact_ref) -> ValidationResult
store_artifact(artifact) -> ObjectRef
register_nexus_asset(manifest) -> NexusAssetRef
reserve_gpu(request) -> LeaseRef
release_gpu(lease_ref) -> None
```

Activities should not hide a large state machine internally. If a service must run a long-lived or independent process, make it its own child workflow or asynchronous activity with heartbeat/cancellation support.

### 6.3 Status projection adapter

Standardize a projection model for UI consumption:

```
submitted
awaiting_approval
queued
running
completed
completed_with_warnings
failed
cancelled
```

Project Temporal state into the application's own database or read model. Preserve the Temporal workflow ID and run ID. Do not force every UI to parse workflow event histories.

---

## 7. Artifact Storage and Publication Contract

### 7.1 Immutable output layout

```
s3://media-artifacts/
  <source-app>/
    <operation>/
      <batch-id>/
        input/
          request.json
          source-manifest.json
        generated/
          <locale>/
            <voice>/
              <node>/
                source.wav
                normalized.wav
                metadata.json
        nexus/
          publication-manifest.json
        manifests/
          batch-result.json
```

### 7.2 Required artifact metadata

Every artifact must carry:
- SHA-256 checksum
- Source script checksum/version
- Voice/reference-audio identifier and checksum
- Engine/model/version
- Generation parameters
- Locale, segment/node, and normalization profile
- Temporal workflow ID/run ID and correlation ID
- Nexus catalog ID after publication

### 7.3 Playback URL contract

The player consumes a **catalog/manifest API**, not arbitrary raw S3 URLs. The API returns signed or proxied playback URLs, enabling:
- Access control and revocation
- Cache policy
- Browser compatibility
- Storage migration without changing the user experience

---

## 8. Governance and Approval

Use a consistent `governance` block in workflow inputs:

```json
{
  "approval_required": true,
  "approval_policy": "publish-public-audio",
  "requested_by": "user_id",
  "reason": "Generate full Japji corpus with force regenerate"
}
```

Workflow behavior is deterministic:
```
validate → estimate scope/cost → wait for approval signal → execute
```

The UI becomes an approval client:
```
POST /api/corpus-batches/{batch_id}/approve
POST /api/corpus-batches/{batch_id}/reject
```

The backend validates authorization and sends a Temporal signal. This creates a durable audit trail even if the UI, pod, or worker restarts.

---

## 9. Observability

### 9.1 Standard metadata

Every workflow and activity must carry:
- `correlation_id`: cross-service trace correlation
- `causation_id`: originating event
- `workflow_id` and `run_id`: Temporal identity
- `source_app`: initiating application
- `tenant_id` and `project_id`: scoping

### 9.2 Metrics

Standard metrics per workflow type:
- `temporal_workflow_started_total{workflow_type, source_app}`
- `temporal_workflow_completed_total{workflow_type, status}`
- `temporal_workflow_duration_seconds{workflow_type}`
- `temporal_activity_duration_seconds{activity_type, task_queue}`
- `temporal_activity_retry_total{activity_type, retry_reason}`
- `temporal_workflow_awaiting_approval_total{workflow_type}`

### 9.3 Logging

Structured logs must include workflow ID, run ID, activity type, attempt number, and correlation ID. Use the platform's standard log format (ADR-027).

---

## 10. Migration Path

### Phase 1: Establish the platform contract (this ADR)

Create a shared package:

```
platform-orchestration-contracts/
  workflow_envelope.py
  workflow_result.py
  artifact_manifest.py
  workflow_ids.py
  temporal_client.py
  event_schemas/
```

Define:
- Workflow envelope and result schema
- Artifact-manifest schema
- Workflow ID convention
- Task-queue naming convention
- Correlation/causation metadata
- Error taxonomy
- Approval signal schema
- Observability labels

### Phase 2: CTS as reference adapter

The CTS Temporal pilot becomes the reference implementation:
- Start one workflow per durable ingestion business process.
- Move "lease wait / retry / worker recovery" into workflow-level state progressively.
- Keep current database job projections for the UI.
- Preserve external `job_id` as the business key.
- Emit standard artifact and completion manifests.

CTS has already identified reusable primitives: atomic claim, retry budget, `next_attempt_at`, lease release, owner identity, task isolation, and terminal cleanup. These belong in platform standards. Temporal may eliminate some local polling and retry machinery once it becomes the primary orchestrator.

### Phase 3: Corpus batch as first cross-app workflow

Implement `CorpusBatchWorkflow v1` wrapping existing orchestration:

```
Casting Signal request
  → Temporal workflow
  → existing submit_japji_temporal_batch.py logic as activity/child workflow
  → generated WAV references
  → Nexus catalog adapter
  → S3 manifest
  → Casting Signal status projection
```

Do not initially duplicate all TTS logic. Wrap and normalize the existing path, then replace internal pieces when stronger durability or observability is needed.

### Phase 4: Standardize artifact publication

Make one canonical `AudioArtifactManifest v1` accepted by Nexus and emitted by CTS, Casting Signal, and ToneRoot. Then "store it the same way ToneRoot does" becomes a testable contract:

```
any producer
  → artifact manifest
  → S3 object storage
  → Nexus registration / conversion
  → catalog record
  → player-ready endpoint
```

### Phase 5: Add cross-app composition

Once each app has stable workflows, compose through:
- Child workflows when a parent owns the overall business outcome.
- Signals when an external actor makes a decision.
- Nexus operations when one workflow needs to invoke a separately owned workflow domain.
- Events only for notification/projection, not as the sole source of a critical command.

---

## 11. Reference Implementations

### 11.1 CTS ingestion (reference adapter)

- **Workflow type**: `media.ingestion.v1`
- **Task queue**: `cts-workflows`
- **Business key**: `job_id` (e.g., `job_20260903211130_5_q`)
- **Workflow ID**: `cts:ingest:job_20260903211130_5_q`
- **State machine**: `pending → leasing → processing → terminal` (database projection)
- **Activities**: `validate_source`, `acquire_whisper_lease`, `transcribe`, `enrich_ollama`, `store_transcript`, `register_nexus`, `release_leases`
- **Current status**: Pilot enabled (`CTS_TEMPORAL_PILOT_ENABLED=true`), worker deployed, database-backed queue worker hardened with atomic claim, durable backoff, and lease release on all failure paths.

### 11.2 Casting Signal corpus batch (target)

- **Workflow type**: `media.corpus-batch.v1`
- **Task queue**: `casting-workflows`
- **Business key**: `batch_id` (e.g., `batch_01JABC`)
- **Workflow ID**: `casting:corpus-batch:batch_01JABC`
- **Child workflows**: one per locale (`casting:corpus-batch:batch_01JABC:locale:en`)
- **Activities**: `validate_corpus_request`, `validate_reference_audio`, `reserve_gpu`, `generate_wav`, `validate_audio`, `store_artifact`, `register_nexus`, `publish_manifest`, `release_gpu`
- **Current status**: Temporal submission script exists but UI is not wired to it. Direct script path produces local files only, no S3 upload, no Nexus registration.

### 11.3 Nexus publication (target)

- **Workflow type**: `media.nexus-publication.v1`
- **Task queue**: `nexus-publication`
- **Business key**: `asset_id` (e.g., `asset_01JXYZ`)
- **Workflow ID**: `nexus:publish:asset_01JXYZ`
- **Activities**: `validate_manifest`, `convert_for_player`, `register_catalog`, `generate_playback_urls`, `update_graph`, `publish_completion`
- **Current status**: `NEXUS_INGEST_ENABLED=false`, no ingest worker deployed.

---

## 12. Consequences

### Positive

- Durable orchestration that survives pod restarts and worker failures.
- Standardized cross-app correlation and audit trail.
- Consistent retry, backoff, and compensation semantics.
- Human approval gates with durable state.
- Per-app isolation via task queues without central ownership of domain logic.
- Testable artifact publication contract across all producers.

### Negative

- Additional infrastructure dependency (Temporal cluster availability).
- Learning curve for apps that have not used Temporal.
- Migration effort to move existing in-process orchestration to workflows.
- Potential for workflow history growth if not managed (use child workflows for fan-out).

### Mitigations

- Temporal cluster is already deployed and used by the CTS pilot.
- Phase 2 (CTS reference adapter) provides a working example for other apps.
- Migration is incremental — existing in-process paths continue working until replaced.
- Child workflows limit parent history size; standard retention policies apply.

---

## 13. Compliance

All applications performing durable, multi-step, cross-boundary work must:
1. Implement the standard workflow input/result envelope.
2. Use the workflow ID convention (`<domain>:<operation>:<business-id>`).
3. Route activities through the appropriate task queue.
4. Store artifacts in S3 with the standard manifest schema.
5. Project workflow status into the local app database for UI consumption.
6. Carry correlation IDs in all logs and metrics.

Applications may continue to use local background workers for short, single-service tasks that do not cross system boundaries and do not require durable state.

---

## 14. References

- [Temporal Task Queues](https://docs.temporal.io/task-queue)
- [Temporal Namespace Management](https://docs.temporal.io/best-practices/managing-namespace)
- ADR-020: GPU Resource Arbitration and Scaling Paradigms
- ADR-028: Service Delivery and Break-Glass Recovery Framework
- ADR-035: CTS Temporal Pilot — Ollama Lease Wiring
- ADR-032: Federated Governance and Evidence Placement

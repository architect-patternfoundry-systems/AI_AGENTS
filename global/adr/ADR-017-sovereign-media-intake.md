# ADR-017: Sovereign Media Intake — Portable Asset Bundles and Multi-Tier Storage

## Status
Accepted

## Design Axiom

> **What travels in a transfer bundle is the asset and its identity, never the permissions that applied to it on the other side.**

Trust is always locally authoritative. No ToneRoot instance inherits permissions from another. A destination instance's permission graph is its own, constructed by a human confirmation step, never bootstrapped automatically from a received bundle.

---

## Context

ToneRoot is a sovereign media database: it accepts music from anywhere, stores it somewhere you own, and makes it available to people you trust. As intake sources multiply (folder drop, rclone-backed cloud storage, scrape-based tools, future partnership push endpoints), two unsolved problems emerge:

1. **Portability**: Assets registered only in PostgreSQL are tied to that instance. If the DB is lost, rebuilt, or the user migrates to a new deployment, asset identity must be reconstructable from S3 alone.

2. **Multi-tier storage**: Not all storage backends are equal. Streaming copies need fast random access (S3/MinIO/R2). Master WAVs need reliable bulk storage but tolerate latency. Archive copies belong on free-tier backends (Google Drive, Backblaze B2) to avoid cost. The system must route assets to tiers and give users advisory when a tier is full before writes happen.

This ADR defines the design decisions governing the Intake Pipeline (Layers 0–5) that addresses both problems.

---

## Reconciliation with ADR-013 (Drop-Folder Worker)

ADR-013 establishes **S3-first, DB-as-projection** for the drop-folder worker. This ADR establishes **DB-first, sidecar-async** for the Ingestion Engine. These are not contradictions — they reflect different execution contexts:

| | Drop-Folder Worker (ADR-013) | Ingestion Engine (this ADR) |
|---|---|---|
| Execution context | Standalone worker process, NFS-mounted | Within backend service, DB always reachable |
| DB availability | Not guaranteed (worker may start before DB) | Guaranteed (FastAPI app health-checked against DB) |
| Authority model | S3 is truth; DB is a projection sync'd later | DB is runtime authority; S3 sidecar is portable identity |
| Failure posture | S3 write failure blocks audio upload | DB write failure aborts intake; sidecar failure is async-retried |

**The drop-folder worker feeds INTO the Ingestion Engine's intake path** via the existing `incoming/` drop-zone. ADR-013's S3-first contract applies to the worker's publish phase. This ADR's DB-first contract applies to the Ingestion Engine's register phase, which consumes the worker's output. They are sequential, not competing.

---

## Decisions

### D1: Two-Write Pattern — DB-First with Async Sidecar

Every intake produces two artifacts:

1. **Media row** (PostgreSQL via `media_registry`) — runtime authority: ownership, permissions, streaming resolution, tier assignment
2. **Portable bundle** (S3 `.toneroot.json` sidecar via `NexusCatalog` v2) — portable identity: travels with the S3 object, survives DB loss, enables cross-instance import

**Write order and failure contract:**

```
Step 1: Write media row to PostgreSQL
         → failure here aborts intake entirely (no partial state)
Step 2: Attempt sidecar write to S3 (best-effort)
         → success: set media.sidecar_written = true
         → failure: leave media.sidecar_written = false, enqueue for BackgroundSidecarWorker
Step 3: BackgroundSidecarWorker retries sidecar_written=false rows with exponential backoff
```

`sidecar_written = false` is **not a degraded state** — the asset is fully functional (streams, permissioned, owned). It is a *portability-pending* state. Operators seeing these rows should treat them as a background queue, not an error.

An S3 object with a `.toneroot.json` sidecar but no corresponding DB row is an **import opportunity**, not an error. The scan-to-import path handles it.

### D2: NexusCatalog v2 Schema

The v2 sidecar schema replaces v1. NexusCatalog v1 has no production writes in any deployed system (confirmed: neither ToneRoot nor StoryLoom call it). No migration tooling is required; v1 is a dead branch.

**v2 sidecar schema** (written to `<audio_key_without_ext>.toneroot.json`):

```json
{
  "schema_version": "2.0.0",
  "id": "<uuid>",
  "title": "...",
  "source_system": "suno | folder_drop | gdrive | bandcamp | import | ...",
  "source_job_id": "<optional>",
  "intake_sha256": "<hex>",
  "audio_key": "path/to/asset.opus",
  "master_key": "path/to/asset.wav",
  "archive_key": "archive/path/to/asset.wav",
  "tiers": {
    "hot":  { "backend": "minio", "bucket": "music",   "key": "...opus" },
    "warm": { "backend": "minio", "bucket": "music",   "key": "...wav"  },
    "cold": { "backend": "gdrive","bucket": "archive", "key": "...wav"  }
  },
  "owner_hint": "<profile_uuid>",
  "trust_hint": ["<grantee_uuid>"],
  "created_at": "<iso8601>",
  "tags": [],
  "provenance": {},
  "audio_format": { "sample_rate": 44100, "channels": 2, "bit_depth": 24, "codec": "wav" },
  "duration_seconds": 0.0,
  "content_length_bytes": 0
}
```

**Trust policy for `owner_hint` / `trust_hint`:** These are suggestions, never authorities. On cross-instance import, the importing user must explicitly confirm or remap ownership. If `owner_hint` references a UUID absent in the destination DB, the import UI offers: (a) map to an existing local profile, or (b) create a new profile shell. No automatic trust escalation occurs. No `media_permissions` row is written without human confirmation.

**NexusCatalog v2 and Ingestion Engine are co-designed.** The canonical call pattern:

```python
# Inside Ingestion Engine, after DB write succeeds:
catalog = NexusCatalog(bucket=tier_assignments["hot"].bucket)
catalog.register_asset(
    bundle=raw_intake_bundle,
    media_id=media_row.id,
    tier_assignments=tier_assignments,
)
```

The schema is validated against this call signature. Do not finalise v2 schema without running the engine's dispatch path against it.

### D3: NexusInventory Retirement

`NexusInventory` (SQLite-backed, `app_lib/nexus_inventory.py`) is retired. It has no production data in any deployed system. `media_registry` PostgreSQL covers its runtime role; the `.toneroot.json` sidecar covers its portability role. The file may be removed from `patternfoundry-applib` after this ADR is accepted.

### D4: storage_configs Multi-Tier Extension

`storage_configs` gains the following columns:

```sql
tier                 TEXT NOT NULL DEFAULT 'hot'  -- 'hot' | 'warm' | 'cold'
capacity_hint_gb     NUMERIC                       -- from last capacity check
capacity_used_gb     NUMERIC                       -- from last capacity check
capacity_checked_at  TIMESTAMPTZ                   -- when capacity was last fetched
```

**Uniqueness constraint:** `UNIQUE(profile_uuid, tier, provider)`. A profile may have one backend per `(tier, provider)` combination — e.g., both MinIO (hot) and R2 (hot) for redundancy. Two MinIO backends at the same tier for the same profile is an operator error. When multiple backends match a tier, the Pre-Flight Advisor assigns to the one with the lowest `capacity_used_gb / capacity_hint_gb` ratio (lowest utilization). Deterministic, not round-robin.

### D5: Pre-Flight Advisor — Capacity Check and Lock Protocol

The Pre-Flight Advisor runs before any intake write. It performs:

1. **Capacity classification** per tier backend:
   - `capacity_checked_at` within 10 minutes AND `batch_size < 100 MB`: use cached values
   - otherwise: re-fetch via rclone rc `about/get`, S3 `HeadBucket`, or Drive `about.get`
   - classify: `SAFE` | `TIGHT` (< 20% headroom) | `BLOCKED` (< batch size available)

2. **Storage assignment**: for each asset in the batch, assign `{asset → tier → backend_config}` based on asset type:
   - opus/mp3 (streaming copy) → `hot`
   - wav/flac (working master) → `warm`
   - wav/flac (archive/backup) → `cold`

3. **Lock protocol** (prevents concurrent over-assignment):

```python
# Fetch capacity BEFORE acquiring lock (slow network call outside lock window)
fresh_capacity = fetch_capacity(backend)

# Acquire row lock — covers only comparison + update, not the network call
with conn.begin():
    row = conn.execute(
        "SELECT * FROM storage_configs WHERE id = :id FOR UPDATE",
        {"id": backend.id}
    )
    # Re-validate with fresh value now that we hold the lock
    if fresh_capacity.available_gb < batch_size_gb:
        raise CapacityBlockedError(backend)
    conn.execute(
        "UPDATE storage_configs SET capacity_used_gb = :used, capacity_checked_at = NOW() ...",
        ...
    )
```

The row lock window covers only the comparison and update — never the external API call. Concurrent intakes serialize on the lock, each re-validating against the freshly fetched value.

If any tier is `BLOCKED`, intake pauses and surfaces the Advisory UI (Option A: skip that asset class; Option B: configure alternate backend; Option C: queue for later as `pinned_tier = 'cold'` on the media row pending cold backend configuration).

### D6: RawIntakeBundle Interface

All intake connectors produce a `RawIntakeBundle`. The Ingestion Engine accepts only this type — connectors never touch S3 or the DB.

```python
@dataclass
class RawIntakeBundle:
    local_path: str            # temp file; caller responsible for cleanup
    sha256: str                # hex digest of raw bytes — computed by connector
    size_bytes: int
    source_system: str         # "folder_drop" | "suno" | "gdrive" | "bandcamp" | "import" | ...
    source_job_id: Optional[str]
    source_url: Optional[str]
    suggested_title: Optional[str]
    suggested_artist: Optional[str]
    suggested_tags: list[str]
    provenance: dict           # source-specific opaque metadata — written to sidecar only, never DB
    mime_type: Optional[str]   # connector hint; engine re-detects from bytes, does not trust this
```

**`provenance` handling:** written to the sidecar's `provenance` field only. Never stored in PostgreSQL as a JSONB column on `media`. The DB stores structured fields (`source_system`, `source_job_id`); unstructured source metadata lives in the portable sidecar. This avoids a stringly-typed opaque blob in the DB.

**Idempotency:** the Ingestion Engine checks `SELECT id FROM media WHERE intake_bundle_sha256 = :sha AND owner_profile_uuid = :owner` before any writes. Match → return existing `media.id`, no-op. This makes all connectors inherently idempotent at the intake layer.

**Engine SHA256 re-verification:** the Ingestion Engine re-computes SHA256 from `bundle.local_path` bytes and asserts it against `bundle.sha256` before doing anything else — before the idempotency check, before any DB write. Connectors can lie, fail mid-copy, or have bugs. The connector-provided hash is never trusted for deduplication without re-verification. This matches the posture of the transfer protocol (D7) which re-verifies received bytes against the sidecar's `intake_sha256`. Intake and transfer must have the same integrity posture.

**Per-user deduplication scope:** `(sha256, owner_profile_uuid)`. The same file imported by two different users creates two independent media rows, two sidecars, and occupies storage twice. This is intentional — each user's sovereign archive is independent. Operators should not be surprised by this. It is documented here as a deliberate choice.

### D7: Transfer Protocol — Token Contract

Cross-instance transfer uses pre-signed URLs mediated by a signed token. No ToneRoot infrastructure sits between source and destination buckets.

**Token fields:**

```json
{
  "token_id": "<uuid>",
  "issued_at": "<iso8601>",
  "expires_at": "<iso8601 — issued_at + 72 hours, hard cap>",
  "scope": ["<asset_uuid>", "..."],
  "source_instance_hint": "<url>",
  "issuer_profile": "<uuid>",
  "hmac_sig": "<HMAC-SHA256 of (sorted asset_uuids + expires_at) using instance transfer-signing-key>"
}
```

**Scope:** always an explicit list of asset UUIDs — never a full-bucket grant. Full-library export = iterate sidecar index, build explicit asset list, issue tokens in batches of 100.

**Signing key:** stored at `secret/toneroot/transfer-signing-key`. Key rotation immediately invalidates all outstanding tokens (by design). Rotation procedure: generate new key, update secret, accept that in-flight transfers must be re-initiated. Document this in runbooks.

**Revocation:** token IDs stored in Redis with TTL = `expires_at`. `DELETE /api/transfer/{token_id}` invalidates immediately. The destination instance checks revocation before fetching each pre-signed URL — not just at transfer start.

**Integrity:** destination verifies `intake_sha256` from the sidecar against the received bytes before writing any DB row. Mismatch → reject, log event, do not write. No silent corruption.

**Pre-signed URL expiry alignment:** the token hard-caps at 72 hours, but pre-signed URLs for the actual object downloads have their own expiry — MinIO and S3 defaults vary and are often shorter. If a destination instance fetches the manifest immediately but streams objects lazily (large library, slow connection), pre-signed URLs issued with a short system default may expire while the token is still valid. **Rule:** pre-signed URLs MUST be issued with `expiry = token.expires_at`, not the backend system default. This applies to both the source instance when issuing URLs and to any tooling that wraps the transfer protocol.

**Trust on import:** `owner_hint` and `trust_hint` from the received sidecar are presented to the importing user for confirmation. No `media_permissions` row is written automatically. See D2 trust policy.

### D8: media Row Extensions

New columns on `media`:

```sql
sidecar_written        BOOLEAN NOT NULL DEFAULT false
source_system          TEXT                            -- matches RawIntakeBundle.source_system
intake_bundle_sha256   TEXT                            -- for idempotency check; indexed
```

Index: `CREATE INDEX ON media (intake_bundle_sha256, owner_profile_uuid)` — covers the idempotency lookup.

---

## Build Order

```
0. This ADR (now)
1. Migration: storage_configs + tier + capacity columns + UNIQUE(profile_uuid, tier, provider)
2. Migration: media + sidecar_written + source_system + intake_bundle_sha256 columns
3. NexusCatalog v2 schema + writer (co-designed with step 4 below)
4. RawIntakeBundle dataclass + Ingestion Engine skeleton (DB write + sidecar dispatch call)
   — steps 3 and 4 iterate together; v2 schema is only final when the engine call compiles
5. BackgroundSidecarWorker (polls sidecar_written=false, retries with exponential backoff)
6. Pre-Flight Advisor (capacity fetch, SELECT FOR UPDATE lock protocol, storage assignment)
7. Advisory UI (intake interstitial: Option A skip, Option B configure, Option C queue)
8. Transfer Protocol (token issuance, pre-signed URL fetch, SHA256 verification, revocation)
```

Items 1–2 are schema-only, no runtime impact. Items 3–5 are backend-only. Items 6–7 are user-visible. Item 8 is a milestone feature.

---

## Connector Capability Reference

| Connector | Protocol | Portable bundle? | Reliability | Notes |
|---|---|---|---|---|
| Folder Drop | filesystem | yes | always | Primary path; never breaks |
| Drop-Folder Worker | inotify + NFS | yes (ADR-013) | always | Feeds Ingestion Engine |
| rclone (Google Drive) | rclone-rc | yes | stable | Rate limits on concurrent range requests; suitable for cold-tier archival only |
| rclone (Dropbox) | rclone-rc | yes | stable | |
| Suno Downloader | scrape | no | low | Fragile by design; maintained, not featured |
| Import API | HTTP POST | yes | caller | Gateway contract per ADR-014 |
| Partnership Push | webhook | yes | partner | Future; same gateway contract |

---

## References

- ADR-013: Drop-Folder Worker (S3-first contract, worker context)
- ADR-014: Ingestion Gateway Contract
- `app_lib/media_registry.py`: `Media`, `StorageConfig`, `register_media()`
- `app_lib/nexus_catalog.py`: v1 implementation (to be replaced by v2)
- `app_lib/nexus_inventory.py`: retired by this ADR

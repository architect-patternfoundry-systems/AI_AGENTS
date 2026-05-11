# ADR-014: Ingestion Gateway Contract

## Status
Proposed

## Context
The drop-folder worker (ADR-013) provides a proven pipeline for processing audio files dropped into `/mnt/data_lake/toneroot/drop-zone/incoming/`. As ToneRoot matures, there may be demand for additional ways to get files into this pipeline beyond direct NFS access.

## Problem Statement
Without a clear contract and phased approach, there is risk of:
- Premature integration surface expansion before the core pipeline is validated in production
- Building gateways that solve problems the system doesn't actually have
- Multiplying operational burden (deployment, monitoring, security) before proven need
- Introducing inconsistent authentication, error handling, and observability patterns

## Decision

### Gateway Contract
**Any ingestion gateway's ONLY job is to write a file + optional `.json` sidecar into `incoming/` and return an acknowledgment.**

The gateway:
- MUST write the file to `/mnt/data_lake/toneroot/drop-zone/incoming/`
- MAY write a `.json` sidecar with metadata
- MUST NOT call `AudioProcessor` or `DBManager` directly
- MUST NOT perform any audio processing or format conversion
- MUST NOT interact with S3 or the database
- MUST return success only when the file is written to `incoming/`
- MUST use the existing `toneroot-secrets` Secret for authentication
- MUST implement rate limiting at the gateway layer
- MUST expose standardized Prometheus metrics

#### Security Requirements for Exposed Gateways
If a gateway is externally exposed (e.g., HTTP upload endpoint accessible from the internet), the following security measures MUST be implemented:

**Virus/Malware Scanning**:
- MUST scan uploaded files with ClamAV or similar antivirus engine before writing to `incoming/`
- MUST quarantine infected files in `/mnt/data_lake/toneroot/drop-zone/quarantine/` with error logs
- MUST reject files that fail virus scan with HTTP 403 or appropriate error code
- MUST update virus definitions daily (via FreshClam or equivalent)
- MUST expose Prometheus metrics for scan results (scanned_files_total, infected_files_total)

**File Type Validation**:
- MUST validate actual file content (not just extension) using `file` command or libmagic
- MUST reject files that don't match declared audio format
- MUST enforce maximum file size (recommended: 500MB for audio files)
- MUST reject executable files, scripts, and non-audio containers

**Authentication and Authorization**:
- MUST require authentication for externally exposed gateways
- MUST implement API key or OAuth2 token validation
- MUST use the existing `toneroot-secrets` Secret for credential storage
- MAY implement per-user quotas and rate limiting

**Network Security**:
- MUST use TLS/SSL for all external communications
- SHOULD be deployed behind a reverse proxy (Traefik/Nginx) with WAF rules
- MAY implement IP whitelisting for trusted sources
- MUST NOT expose the raw NFS mount to external networks

**Audit Logging**:
- MUST log all upload attempts with timestamp, source IP, authentication identity, and file hash
- MUST retain audit logs for minimum 90 days
- MUST alert on repeated failed authentication attempts or virus detection events

**Implementation Note**: For the initial Phase 1 HTTP gateway, if only exposed internally (within the tailnet), virus scanning MAY be deferred until external exposure is required. However, file type validation and authentication should be implemented from the start.

#### Supported Input File Formats
The drop-folder worker uses FFmpeg for audio processing, which supports virtually all common audio formats. Supported input formats include:

- **Common**: MP3, WAV, FLAC, OGG, M4A, AAC, WMA, AIFF
- **Professional**: ALAC, DSD, DSF, DFF
- **Legacy**: AC3, DTS, MP2, PCM
- **Container-based**: MKV, AVI, MOV (audio stream extraction)
- **Streaming**: HTTP/RTMP URLs (if gateway provides URL instead of file)

**Note**: The worker automatically converts all inputs to three standardized output formats (WAV, MP3, Opus) regardless of input format.

#### Metadata Sidecar Schema
Gateways MAY write a `.json` sidecar alongside the audio file to provide metadata. The sidecar filename must match the audio filename with `.json` appended.

**Example**: `my_song.mp3` → `my_song.mp3.json`

**Supported Metadata Fields**:

```json
{
  "title": "My Song Title",
  "artist": "Artist Name",
  "genre": "Electronic",
  "album": "Album Name",
  "year": 2024,
  "bpm": 120,
  "key": "C minor",
  "lyrics": "Lyrics text here",
  "lyrics_sync": [
    {"time": 0.0, "text": "First line"},
    {"time": 2.5, "text": "Second line"}
  ],
  "tags": ["ambient", "chill", "focus"],
  "source": "user_provided",
  "custom_field": "Any additional fields are preserved in metadata_json"
}
```

**Field Descriptions**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | No | Song title. If omitted, extracted from filename |
| `artist` | string | No | Artist name |
| `genre` | string | No | Musical genre |
| `album` | string | No | Album name |
| `year` | integer | No | Release year |
| `bpm` | integer | No | Tempo in beats per minute |
| `key` | string | No | Musical key (e.g., "C minor", "F# major") |
| `lyrics` | string | No | Plain text lyrics |
| `lyrics_sync` | array | No | Synchronized lyrics with timestamps (see format below) |
| `tags` | array | No | Array of string tags for categorization |
| `source` | string | No | Metadata source identifier (e.g., "user_provided", "filename_convention") |
| `*` | any | No | Any additional fields are preserved in `metadata_json` |

**lyrics_sync Format**:
```json
[
  {"time": 0.0, "text": "First line of lyrics"},
  {"time": 2.5, "text": "Second line of lyrics"},
  {"time": 5.0, "text": "Third line of lyrics"}
]
```

**Filename Convention Fallback**:
If no sidecar is provided, the worker attempts to extract metadata from the filename using the pattern: `title--artist--genre.ext`

Example: `my_song--Artist Name--Electronic.mp3` → title="my_song", artist="Artist Name", genre="Electronic"

**Metadata Processing**:
- All provided fields are merged with worker-generated metadata (`processed_at`, `source_system`)
- The `lyrics_sync` field is automatically promoted to top-level metadata for DB integration
- Additional custom fields are preserved in the `metadata_json` column in the database
- The worker adds `processed_at` timestamp and `source_system: "drop-folder"` automatically

#### Operational Semantics

**Order of Operations and File Matching**

**Scenario 1: Audio file dropped before JSON sidecar**
- **Current behavior**: Worker processes audio file immediately using filename fallback
- **Issue**: JSON sidecar arrives later but is ignored (audio already processed)
- **Recommended behavior**:
  - Worker should wait up to 30 seconds for sidecar before processing without it
  - If sidecar arrives during wait period, use it
  - If sidecar arrives after processing, metadata update requires separate enrichment service
  - Gateways SHOULD upload both file and sidecar in single atomic operation

**Scenario 2: JSON sidecar dropped before audio file**
- **Current behavior**: JSON sidecar sits in `incoming/` until audio file arrives
- **Recommended behavior**:
  - Worker ignores orphaned sidecars (no matching audio file)
  - Orphaned sidecars older than 1 hour are moved to `failed/` with error log
  - Gateways SHOULD upload audio file first, then sidecar

**Scenario 3: Filename mismatch (audio.mp3 vs metadata.json)**
- **Current behavior**: Sidecar not associated (only exact filename match)
- **Recommended behavior**:
  - **Strict mode** (recommended): Reject sidecars that don't match audio filename exactly
  - **Lenient mode** (optional): Allow pattern matching (e.g., `audio.*.json` matches `audio.mp3`)
  - Gateways MUST ensure sidecar filename matches audio filename exactly
  - Mismatched sidecars moved to `failed/` with error log

**Scenario 4: Multiple files with same name**
- **Current behavior**: Advisory locking prevents concurrent processing, second file waits
- **Recommended behavior**:
  - If content is identical (same hash), second file is deduplication (ignored)
  - If content differs, second file processed as new version (different UUID)
  - Gateways SHOULD reject duplicate filenames to avoid confusion
  - Or gateways SHOULD append timestamp to prevent collisions: `file_20240110_143022.mp3`

**Scenario 5: Non-file gateway clients (HTTP, API)**
- **Recommended behavior**:
  - MUST send both file and metadata in single atomic request
  - MUST NOT support separate file/metadata upload requests (prevents race conditions)
  - MUST validate that both are present before accepting upload
  - MUST return error if either is missing

#### File Naming Conventions

**Strict Filename Matching (Recommended for File-Based Gateways)**
```
audio_file.mp3        → audio_file.mp3.json
my_song--Artist--Genre.mp3  → my_song--Artist--Genre.mp3.json
```

**UUID-Based Matching (Alternative for Advanced Gateways)**
- Gateway generates UUID, uploads both with same UUID prefix
- Worker matches by UUID instead of filename
- More flexible but requires gateway coordination

#### Acknowledgment and Notification Mechanisms

**Immediate ACK (File Receipt)**
- Gateway returns HTTP 200/OK immediately after successful write to `incoming/`
- ACK confirms file reached drop zone, NOT that processing is complete
- ACK includes: `upload_id`, `filename`, `timestamp`, `estimated_processing_time`

**Asynchronous Processing Notification**
Current implementation has NO notification mechanism. Recommended options:

**Option 1: Webhook Callback (Recommended)**
- Gateway accepts optional callback_url parameter
- Worker POSTs to callback_url when processing completes
- Simple, widely supported, works across firewalls

**Option 2: Database Polling**
- Client queries database for processing status
- Check metadata fields for completion indicators
- Simple but requires client polling logic

**Option 3: Message Queue (Kafka/RabbitMQ)**
- Worker publishes events to message queue on completion
- Client subscribes to queue for notifications
- More complex but scalable for high-volume scenarios

**Option 4: WebSocket Subscription**
- Client opens WebSocket connection to gateway
- Gateway forwards worker events to connected clients
- Real-time but requires persistent connection

**Recommended Implementation**:
- Phase 1: Implement webhook callback for HTTP gateway
- Phase 2: Add database polling documentation for alternative approach
- Phase 3: Consider message queue for high-volume scenarios

#### Error Handling and Retry Policy

**Gateway-Level Errors**
- Invalid file format: Reject immediately with 400 Bad Request
- Missing required metadata: Reject immediately with 400 Bad Request
- Virus scan failure: Reject with 403 Forbidden, quarantine file
- Rate limit exceeded: Reject with 429 Too Many Requests

**Worker-Level Errors**
- Processing failure: Move to `failed/` with error log
- S3 upload failure: Retry 3 times with exponential backoff
- DB upsert failure: Log warning, continue (sync job will handle)

**Client Retry Policy**
- Gateway ACK timeout: Retry upload with new filename (append timestamp)
- Processing failure: Check `failed/` directory, fix issue, re-upload
- Webhook delivery failure: Worker should retry webhook 3 times

#### Current Metadata Enrichment Capabilities

**At Ingestion Time (Drop-Folder Worker):**
- **Minimal enrichment**: Worker only adds `processed_at` timestamp and `source_system` fields
- **No transcription**: Drop-folder worker does NOT automatically trigger Whisper transcription
- **No audio analysis**: No BPM detection, key detection, or audio feature extraction
- **Metadata preservation**: All user-provided metadata is passed through unchanged

**Post-Ingestion Enrichment (Manual/Optional):**
- **Whisper Transcription**: Available via ToneRoot IPC service (`lyrics.transcribe` call)
  - Triggered manually through ToneRoot UI or IPC
  - Requires audio to be accessible via S3
  - Produces `lyrics_sync` with timestamped segments
  - Stored in database `metadata_json.lyrics_sync` column
  - NOT automatically triggered by drop-folder uploads

**Future Automated Enrichment (Not Implemented):**
- **Automatic transcription**: Could be added to drop-folder worker or separate enrichment service
- **Audio feature extraction**: BPM, key, genre classification, mood detection
- **Metadata lookup**: MusicBrainz, Discogs integration for artist/album/track metadata
- **Lyrics fetching**: Genius, LyricWiki integration (if not transcribed)
- **Audio quality analysis**: Dynamic range, clipping detection, noise assessment

#### Metadata Update Strategy

**Current State (Manual):**
1. File dropped → worker processes → uploads to S3 → basic DB entry
2. User opens ToneRoot → manually triggers transcription via UI
3. TranscriptionWorker processes → updates DB with `lyrics_sync`
4. User can manually edit metadata in ToneRoot UI

**Recommended Future State (Automated):**
Consider implementing a separate **metadata enrichment service** that:

1. **Listens for new drop-folder uploads** (via S3 events or database triggers)
2. **Automatically triggers transcription** for new audio files
3. **Performs audio feature extraction** (BPM, key, genre)
4. **Enriches metadata** from external sources (MusicBrainz, etc.)
5. **Updates database** with enriched metadata
6. **Emits events** for UI updates

This would keep the drop-folder worker simple (ingestion-only) while providing automated enrichment as a separate concern.

The worker (ADR-013) remains responsible for:
- Claiming files from `incoming/`
- Audio processing and format conversion
- S3 uploads
- Database upserts
- All downstream state management

### Approved Phase 1 Gateways
**Only the following gateways are approved for implementation until the drop-folder worker has 30 days of production operation:**

1. **HTTP Upload Endpoint**
   - Lightweight Flask/FastAPI service
   - POST /upload with multipart/form-data
   - Optional metadata as form fields or JSON sidecar
   - Rate limiting per IP
   - CORS support

2. **CLI Tool**
   - Simple Python CLI for automation
   - Direct file copy to NFS mount or HTTP upload
   - Metadata via CLI flags or JSON file
   - Scriptable for CI/CD pipelines

**Rationale:** These are stateless, testable, compose cleanly with the existing worker, and provide immediate value for the single-user homelab use case.

### Deferred Gateways
All other integration options are explicitly deferred with revisit conditions:

| Gateway | Revisit Condition |
|---------|-------------------|
| SFTP Server | If ToneRoot is shared with other users or professional audio workflows emerge |
| WebDAV Server | If OS-native mounting is requested by multiple users |
| rsync Daemon | If large fileset syncing becomes a regular use case |
| Slack/Discord Bots | If ToneRoot is adopted by a team using these platforms |
| Email Gateway | If async email-based submission is requested |
| S3-Compatible API | If cloud-native workflows or S3 SDK integration is needed |
| Mobile App | If mobile recording/on-the-go use cases emerge |
| WebRTC Recording | If browser-based recording is requested |
| YouTube/SoundCloud | If content extraction from these platforms is needed |
| Kafka/RabbitMQ | If ingest volume exceeds 100 files/day or event-driven architecture is required |
| IPFS/libp2p | If decentralized storage use cases emerge |

## Consequences

### Positive
- Clear separation of concerns: gateways ingest, worker processes
- Prevents operational burden multiplication before proven need
- Standardized authentication (single `toneroot-secrets` Secret)
- Standardized observability (Prometheus metrics)
- Rate limiting at gateway prevents worker overwhelm
- Easy to add new gateways once contract is established

### Negative
- Some potentially useful integrations are deferred
- Requires explicit revisit decisions rather than ad-hoc implementation
- Single-user system may feel "limited" compared to comprehensive integration surface

### Operational Implications
- Each gateway is a lightweight stateless service
- No additional database connections or queues
- Minimal monitoring burden (standardized metrics)
- Authentication handled centrally via `toneroot-secrets`
- Rate limiting prevents backpressure issues in worker

## Implementation Notes for Phase 1

### HTTP Upload Gateway
```yaml
# deployment: http-upload-gateway
- Image: python:3.11-slim with Flask/FastAPI
- Replicas: 2 (for availability)
- Resources: 128Mi memory, 100m CPU
- Env vars from toneroot-config ConfigMap
- Secrets from toneroot-secrets Secret
- NFS mount for direct write to incoming/
- Rate limit: 10 uploads/minute per IP
- Max file size: 500MB
- Prometheus metrics on port 9102
- Security:
  - ClamAV sidecar for virus scanning (if externally exposed)
  - File type validation using libmagic
  - TLS termination via Traefik
  - API key authentication

# API Specification (Phase 1)
POST /upload
- Request: multipart/form-data
  - file: audio_file (required)
  - metadata: JSON string (optional, but recommended)
  - callback_url: webhook URL (optional, for async notification)
- Response: 200 OK
  - upload_id: UUID
  - filename: original filename
  - timestamp: ISO8601
  - estimated_processing_time: seconds
- Validation:
  - Both file and metadata in single request (atomic)
  - Reject if file type validation fails
  - Reject if virus scan fails (if enabled)
  - Reject if rate limit exceeded

# Webhook Callback (async notification)
POST {callback_url}
- Request body:
  - upload_id: UUID
  - status: success | failed
  - audio_uuid: content-hash UUID
  - s3_key: S3 key for primary audio
  - derivatives: list of derivative S3 keys
  - error: null or error message
  - processed_at: ISO8601 timestamp
- Retry policy: 3 attempts with exponential backoff
```

### CLI Tool
```bash
# toneroot-upload CLI (client-side, no deployment)
toneroot-upload file.mp3 --metadata artist="Artist" --title="Song"
toneroot-upload --watch ./audio/
toneroot-upload --nfs-path /mnt/data_lake/toneroot/drop-zone/incoming/
toneroot-upload --http-url https://upload.toneroot.local

# CLI should enforce:
# - Upload both file and metadata in single operation
# - Validate filename matching if uploading sidecar separately
# - Append timestamp to prevent filename collisions
# - Return upload_id for tracking
# - Support --callback-url for async notification
```

## Success Criteria
- Phase 1 gateways implemented and tested
- Drop-folder worker operates for 30 days in production
- No operational incidents caused by gateway layer
- Clear user demand emerges for at least one deferred gateway before expanding scope

## References
- ADR-013: Drop-Folder Worker Architecture
- ToneRoot SDD Stage 4 (current validation phase)
- AGENTS.md: Infrastructure governance and operational standards
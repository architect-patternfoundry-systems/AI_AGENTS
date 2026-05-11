# ADR-013: Drop-Folder Worker Architecture

## Status
Implemented

## Overview
Drop-folder mechanism for ToneRoot that allows users to drop audio files into `/mnt/data_lake/toneroot/drop-zone/incoming/` on cortex, which are then processed through the existing ToneRoot pipeline and made accessible through ToneRoot.

## Critical Design Decisions
- **S3-First Contract**: `.json` sidecar written to S3 BEFORE audio uploads (DB is projection, not authority)
- **Content-Hash UUID**: Deterministic UUIDs from SHA256 hash to prevent duplicates on worker restart. **NOTE**: This causes file-level deduplication - identical files from different users will produce the same UUID and overwrite each other's metadata. Acceptable for single-user homelab, but intentional choice for multi-user contexts.
- **Single-Replica Deployment**: Prevents race conditions on file claiming. **GUARD RAIL**: Flux kustomization patch enforces `spec.replicas: 1` to continuously reconcile against manual scaling.
- **Polling over inotify**: Reliable for cross-host NFS
- **Health Check Location**: Must write to `/mnt/data_lake/toneroot/drop-zone/.health_check` (NOT incoming/)
- **Sidecar Lifecycle**: Metadata sidecar moved to staging with audio file, only deleted after successful S3 publish to preserve metadata on failure
- **Audit Trail**: Lightweight append-only log at `.processed.log` for operational auditing
- **Advisory Locking**: File-level `.lock` files with stale lock detection (30-minute threshold)
- **Best-Effort DB**: S3 is authoritative; DB upsert attempted for low-latency visibility but sync job handles consistency

## Folder Structure
```
/mnt/data_lake/toneroot/drop-zone/
├── incoming/              # User drops files here
├── processing/            # Files being actively processed
│   ├── .lock/            # Advisory lock files
│   └── .staging/         # Temporary conversion workspace
├── failed/               # Failed processing with error logs (UUID suffix prevents collisions)
├── quarantine/            # Virus-infected files (if gateway implements scanning)
├── .health_check         # Health check file (sibling to incoming/)
└── .processed.log        # Append-only audit log (UUID + original filename)
```

## Deployment Notes
- **Replicas**: Must be 1 (single-replica to prevent race conditions). **ENFORCED** via Flux kustomization patch `spec.replicas: 1` to continuously reconcile against manual scaling.
- **Namespace**: `toneroot` (not default)
- **Health Registry**: `http://health-registry.toneroot.svc.cluster.local`
- **Poll Interval**: 30 seconds (configurable via DROP_ZONE_POLL_INTERVAL)
- **NFS Server**: Hardcoded in deployment.yaml (cortex.tailc2cafc.ts.net) per AGENTS.md. Flux substitution via ${NFS_SERVER} is alternative.
- **Prometheus Port**: 9101 (to avoid conflicts with existing services)
- **Security**: S3 credentials must be configured via Secrets, no hardcoded defaults (worker will fail fast if missing)

## Implementation Details

### Security Considerations
- **Virus Scanning**: If gateways are externally exposed, MUST implement ClamAV scanning before files reach `incoming/`. Infected files are quarantined in `quarantine/` directory.
- **File Type Validation**: Gateways MUST validate actual file content (not just extension) using libmagic before writing to `incoming/`.
- **Authentication**: Exposed gateways MUST require authentication via API keys or OAuth2, using the existing `toneroot-secrets` Secret.
- **Network Security**: Exposed gateways MUST use TLS/SSL and SHOULD be deployed behind Traefik with WAF rules.
- **Audit Logging**: All upload attempts MUST be logged with timestamp, source IP, authentication identity, and file hash (retained 90 days minimum).

**Note**: For internal-only gateways (e.g., within tailnet), virus scanning MAY be deferred until external exposure is required. However, file type validation and authentication should be implemented from the start.

### Worker Lifecycle
1. **Claim Phase**: Atomically create `.lock` file, move file to `.staging/` with sidecar
2. **Process Phase**: Convert to WAV/MP3/Opus using AudioProcessor, generate content-hash UUID
3. **Publish Phase**: Write `.json` sidecar to S3 FIRST, then upload audio derivatives
4. **Cleanup Phase**: On success, remove staging files and lock. On failure, move to `failed/` with error log.

### Bug Fixes Applied (Production-Ready v5)
1. **Syntax Error**: Fixed stray closing parenthesis in `processing_attempts_total.labels(status='failed').inc()`
2. **Finally Block Double-Cleanup**: Added `success` flag to prevent metadata loss on failure; cleanup only runs on success
3. **Metadata Sidecar Location**: Sidecar now moved to staging with audio file, deleted only after successful processing
4. **Stale Lock Cleanup**: Stale lock files cleaned up immediately after successful claim
5. **boto3 Import**: Fixed to use `botocore.config.Config` instead of `boto3.session.Config`
6. **Missing Import**: Added `import requests` for health registry integration
7. **Credential Defaults**: Removed hardcoded defaults, worker fails fast if credentials missing
8. **Logger Initialization**: Moved logging setup before credential validation to prevent NameError
9. **NFS Volume Spec**: Hardcoded `server: cortex.tailc2cafc.ts.net` (non-existent `serverFrom` field removed)
10. **Filename Collision**: Added UUID suffix to failed filenames for collision prevention
11. **Kustomization Structure**: Separated Flux Kustomization CR from Deployment YAML

### Prometheus Metrics
- `drop_zone_processing_attempts_total{status}`: claimed/success/failed/error counts
- `drop_zone_processing_duration_seconds`: Histogram of processing times
- `drop_zone_failed_files_count`: Gauge of files in failed directory
- `drop_zone_nfs_health_status`: 1=healthy, 0=unhealthy
- `drop_zone_missing_derivatives_total{format}`: Count of failed derivative uploads
- `drop_zone_db_upsert_skipped_total{reason}`: DB fallback tracking

### Error Handling Strategy
- **NFS Degradation**: 3 consecutive health check failures trigger DEGRADED signal to health registry
- **S3 Failures**: Metadata sidecar write failure prevents audio uploads; partial derivative uploads tracked via metrics
- **DB Failures**: Non-blocking; sync job ensures eventual consistency
- **Stale Locks**: Automatic cleanup on claim with 30-minute threshold
- **Failed Files**: Moved to dead-letter queue with error logs, UUID suffix prevents overwrites

### Metadata Conventions
Filename convention supported: `my_song--Artist Name--Genre.mp3`
- Fallback: Title extracted from filename (underscores/dashes converted to spaces, title-cased)
- Sidecar: Optional `.json` file alongside audio provides additional metadata

## References
- Implementation: `/home/cortex/workspace/infrastructure/apps/toneroot/drop-folder-worker/`
- ADR-014: Ingestion Gateway Contract
# ADR 021: Staged Commit Architecture for Avatar Generation

## Status
Accepted

## Context
Character avatar generation historically utilized a "3 candidates" pattern. While this amortized cold-start latency (30-90s), it created a fragile dependency chain where backend persistence relied on client-side state. If a user generated candidates but navigated away before selecting one, no canonical asset was saved to the Neo4j graph. 

As we modernize to a unified GPU-accelerated batch pipeline (`avatar_job.py`), we need a resilient pattern that balances the UX benefits of latency hedging with robust, disconnected backend persistence.

## Decision
We will adopt a **Staged Commit** architecture utilizing S3 Bucket Lifecycle policies for asynchronous garbage collection.

1. **Generation (Candidate Mode)**: Candidate images are generated (N=2) and uploaded to MinIO/S3 under a `temp/character_avatar/` prefix. Neo4j is *not* updated.
2. **Commit**: The UI submits the selected S3 `temp/` key to a new `/api/graph/avatars/commit-candidate` endpoint.
3. **Persistence**: The commit endpoint copies the selected object from `temp/character_avatar/` to `character_avatar/`, and only after the copy succeeds does it update the Neo4j node's `portrait_url` property via a `SET` clause.
4. **Cleanup**: An S3 Bucket Lifecycle rule will be configured to unconditionally expire any object in the `temp/` prefix after 24 hours. The commit endpoint may optionally enqueue a best-effort `DeleteObject` for the temporary keys as a courtesy optimization.

## Alternatives Considered
* **Option A: Optimistic Single with Fast Regenerate**: Generate 1 asset, immediately commit it to Neo4j, and offer "Regenerate". Rejected for Phase 1 because current GPU cold-start times (90s) make the cost of a "bad" initial generation too high.
* **Option B (Leave-in-Place)**: Keep the S3 object in the `temp/` prefix, but update Neo4j. Rejected because S3 lifecycle rules are prefix-based. A 24-hour expiration rule on `temp/` would eventually delete canonical committed assets. Tag-based exceptions were deemed too complex.

## Failure Modes
* **Client Disconnect**: If the client disconnects before committing, the `temp/` assets safely expire after 24 hours. No orphan records pollute Neo4j.
* **Copy succeeds, graph update fails**: The permanent asset exists but the graph still points to the previous value or null. The endpoint should be idempotent and retryable; the client can retry the commit request without side effects.
* **Best-Effort Delete Fails**: If the UI/backend courtesy deletion fails, the 24-hour lifecycle policy acts as an absolute backstop.
* **Commit Malicious/Invalid Key**: The commit endpoint validates that the input key explicitly belongs to the `temp/` namespace before performing the copy.

## Rollout Steps
1. Add `mode="candidate"` support to `avatar_job.py` to upload to the `temp/` prefix.
2. Build the `POST /api/graph/avatars/commit-candidate` endpoint with copy-then-set behavior.
3. Update `CharacterStudio.jsx` overlay to use candidate mode and call the commit endpoint.
4. Infrastructure updates the MinIO bucket configuration with the 24h `temp/` expiration lifecycle rule (only applied after staging validation to prevent accidental deletions).

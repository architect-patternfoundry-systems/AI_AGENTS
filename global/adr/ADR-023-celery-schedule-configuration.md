# ADR-023: Celery Schedule Configuration

**Date:** 2026-07-02
**Status:** Accepted

## Context
The ToneRoot backend uses Celery Beat for periodic tasks (lyrics reconciliation, nightly transcription, KEDA signal reconciliation, semantic retry). The current implementation hardcodes schedules in `api.py` under the `beat_schedule` configuration. An alternative is DB-backed dynamic scheduling via `django-celery-beat`, which allows runtime modification but adds complexity.

## Decision
Keep Celery Beat schedules in code (`api.py`) for initial release. Defer DB-backed dynamic scheduling to v2.

## Consequences
- **Positive:** Simpler deployment, no additional dependencies, no database migration needed. Schedules are version-controlled with the codebase.
- **Negative:** Schedule changes require code deploy and restart. Non-technical users cannot modify schedules without backend access.
- **Neutral:** Current schedule count (4 tasks) does not justify dynamic scheduling overhead. The admin UI can still expose "Run now" buttons and show queue depth without touching schedule config.

## Compliance
Schedules remain in `api.py` under `beat_schedule` dict using `crontab()` objects from `celery.schedules`. Any future addition of >8 periodic tasks or requirement for non-technical schedule modification triggers ADR revisitation.

## Related
- ADR-018: KEDA-Flux-Tilt Arbitration (deployment model)

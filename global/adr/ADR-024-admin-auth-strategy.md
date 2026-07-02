# ADR-024: Admin Authentication Strategy

**Date:** 2026-07-02
**Status:** Accepted

## Context
The ToneRoot admin UI exposes sensitive operations (reconciliation triggers, file deletion, queue management, user impersonation). Access must be restricted to authorized users. Options include:
1. RBAC with database roles and permissions
2. `ADMIN_USERS` environment variable list
3. No auth (home lab only)

## Decision
Use an `ADMIN_USERS` environment variable containing a comma-separated list of authorized email addresses. Middleware on all `/admin/*` routes rejects requests where `request.user.email` is not in the list.

## Consequences
- **Positive:** Simple deployment (env var only), no database migration, no additional tables. Fits existing env-driven configuration pattern (Ollama, Tailscale, GPU config).
- **Negative:** Requires restart to change admin list. No per-permission granularity (binary: admin or not). User impersonation requires audit trail (see ADR-025).
- **Neutral:** Sufficient for home lab deployment. Multi-tenant deployments would require RBAC upgrade.

## Compliance
All views under `/admin/*` must be decorated with or protected by `AdminAuthMiddleware`. The middleware checks `request.user.email` against the `ADMIN_USERS` env var and returns 403 Forbidden for unauthorized access. Any addition of permission-based access control (e.g., "can delete files" vs "can view dashboard") triggers ADR revisitation.

## Related
- ADR-022: SMB-First Auth Strategy (tiered auth model)

# Incident: Credential Exposure — CTS Database and MinIO Passwords

**Date**: 2026-09-05
**Severity**: High
**Status**: Active — remediation committed, rotation pending operator action
**Reporter**: Agent session (ADR-036 review)
**Assignee**: Infrastructure Team

## Summary

A live database credential was present in shell commands in a conversation transcript. Investigation revealed that the PostgreSQL app password and MinIO root password were hardcoded across multiple files in the CTS repository and had been since initial deployment. An earlier remediation effort (branch `security/comprehensive-secret-remediation`, PR #1) partially addressed this but was never merged.

**Exposed values**: The actual credential values are recorded in the prior secret inventory (`docs/artifacts/secret-inventory.md` on the `security/comprehensive-secret-remediation` branch). They are redacted here to avoid further propagation.

## Timeline

| Time | Event |
|---|---|
| Pre-2026-08-26 | Passwords hardcoded in CTS deploy-dev.yaml, start_cts.sh, db_migrator.py, env.py, alembic.ini |
| 2026-08-26 | Secret inventory created on `security/comprehensive-secret-remediation` branch documenting 65 findings |
| 2026-08-26 | PostgreSQL password replaced with secretKeyRef on security branch (commit `0f3e84c`) |
| 2026-08-26 | Remediation documentation added (commit `49dc80b`) |
| Post-2026-08-26 | Security branch never merged; work stalled |
| 2026-09-04 | ADR-035 dependency audit noted the exposed credential in shell commands |
| 2026-09-05 | ADR-036 review identified the same exposure and required rotation |
| 2026-09-05 | This incident opened; complete remediation committed on `security/complete-secret-remediation` branch |

## Affected systems

- **CTS backend** (`cts-backend` deployment) — PostgreSQL and MinIO credentials in env vars
- **CTS temporal worker** (sidecar) — PostgreSQL and MinIO credentials in env vars
- **CTS DLQ replay** (sidecar) — PostgreSQL credential in env vars
- **CTS watchdog** (deployment) — PostgreSQL and MinIO credentials in env vars
- **CTS startup script** (`start_cts.sh`) — PostgreSQL password exported
- **CTS migration code** (`db_migrator.py`, `env.py`) — PostgreSQL password as default
- **CTS Alembic config** (`alembic.ini`) — PostgreSQL password in connection URL

## Root cause

1. Credentials were initially hardcoded for development convenience.
2. No pre-commit hook or CI check prevented credential commits.
3. The remediation branch was created but never merged due to conflicting work on the Temporal pilot.
4. The security branch diverged from main and became stale.

## Remediation taken

### Code changes (committed on `security/complete-secret-remediation`)

1. `deploy-dev.yaml` — all PostgreSQL DSN and PG_PASS values replaced with `secretKeyRef` from `cts-db-secret`
2. `deploy-dev.yaml` — all MinIO AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY values replaced with `secretKeyRef` from `cts-minio-secret`
3. `deploy-dev.yaml` — added header documentation with secret creation commands
4. `start_cts.sh` — PG_PASS now requires `POSTGRES_PASSWORD` env var (fails if unset)
5. `src/ingestion/db_migrator.py` — removed hardcoded default, requires env var
6. `src/database/migrations/env.py` — removed hardcoded default, requires env var
7. `alembic.ini` — password replaced with `<POSTGRES_PASSWORD>` placeholder
8. `.gitleaks.toml` — added project-specific secret detection rules
9. Pre-commit hook updated to run gitleaks on staged changes

### Preventative mechanisms

1. **Pre-commit gitleaks hook** — scans staged diff before each commit, blocks if secrets detected
2. **`.gitleaks.toml`** — custom rules for PostgreSQL DSN, MinIO keys, PG_PASS literals
3. **`scan_workspace_credentials.py`** — workspace-wide scanner for known exposed values and pattern-based detection
4. **Secret remediation runbook** — step-by-step rotation and verification procedure

## Required operator actions (NOT yet done)

1. **Rotate PostgreSQL app password** — see `docs/artifacts/secret-remediation-runbook.md` section 3.1
2. **Rotate MinIO root password or create scoped SA** — see runbook section 3.2
3. **Create Kubernetes Secrets** — `cts-db-secret` and `cts-minio-secret` in `cts` namespace
4. **Restart CTS pods** — to pick up new secrets
5. **Verify** — health checks, DB connectivity, S3 connectivity, queue worker
6. **Clean shell history** — remove old password from `~/.bash_history`
7. **Update scanner** — remove old values from `KNOWN_EXPOSED_VALUES` in `scan_workspace_credentials.py`

## Prevention

| Mechanism | Status | Description |
|---|---|---|
| Pre-commit gitleaks hook | Deployed (CTS) | Blocks commits containing secrets |
| `.gitleaks.toml` config | Deployed (CTS) | Custom rules for project-specific patterns |
| Workspace credential scanner | Deployed (AI_AGENTS) | Manual/CI scanner for all repos |
| Secret remediation runbook | Created (CTS) | Rotation procedure for operators |
| Kubernetes Secret migration | Committed (CTS) | All env vars use secretKeyRef |
| Python default removal | Committed (CTS) | No hardcoded password defaults |

## Cross-repo impact

The same PostgreSQL password appears in `application`, `infrastructure_check`, and `neural_mesh_canvas`. Rotating the password in PostgreSQL will affect all these repos. Each repo needs its own secret remediation. The scanner identifies all locations.

## Lessons learned

1. **Security branches must be merged promptly** — the `security/comprehensive-secret-remediation` branch sat for 10 days without merging and became stale.
2. **Pre-commit hooks must be in place before the first commit** — not added reactively after exposure.
3. **Credentials should never be in defaults** — Python `os.getenv("PG_PASS", "literal")` is as bad as hardcoding in YAML.
4. **Shell command transcripts are a credential exposure vector** — agents and operators must not paste DSNs with passwords into commands, logs, or chat.
5. **Secret rotation must be verified** — creating a remediation branch without rotating the actual password leaves the system exposed.

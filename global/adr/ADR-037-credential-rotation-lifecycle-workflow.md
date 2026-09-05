# ADR-037: Credential Rotation Lifecycle Workflow

**Status:** Proposed
**Date:** 2026-09-05
**Author:** Platform Team
**Category:** Security
**Related:** ADR-032 (Federated Governance), ADR-036 (Temporal Integration Standard)

---

## 1. Context

ADR-036 established the Temporal integration standard for cross-app durable orchestration. A live database credential exposure incident (2026-09-05) demonstrated that credential rotation is currently a manual, error-prone process with no verification, no rollback safety, and no audit trail. The existing remediation (CTS PR #4) moved hardcoded credentials to Kubernetes `secretKeyRef`, but the actual rotation still requires an operator to change a password and hope applications recover.

The platform needs credential rotation treated as a **durable workflow** — not a cron job that changes a password and leaves recovery to chance. A Temporal workflow can coordinate safe rollout, health verification, revocation, and compensation, with full audit evidence.

## 2. Decision

Define a standard `CredentialRotationWorkflow v1` that orchestrates the full credential lifecycle using Temporal, with provider-specific activity adapters and a secret-safe contract that never embeds credential values in workflow history.

### 2.1 Separation of responsibilities

```text
Policy / schedule / security event
          │
          ▼
Temporal CredentialRotationWorkflow
          │
          ├── assess scope and select rotation strategy
          ├── generate or request new credential
          ├── stage secret in secret authority
          ├── synchronize workload-facing secret
          ├── roll/reload consumers safely
          ├── verify new credentials end-to-end
          ├── drain/revoke old credential
          ├── audit outcome and notify
          └── compensate / escalate on failure
          │
          ▼
Secret authority + identity provider
          │
          ├── Vault / cloud secret manager / protected Secret backend
          ├── PostgreSQL roles
          ├── MinIO service accounts
          ├── third-party API credential providers
          └── certificate/signing-key systems
          │
          ▼
External Secrets Operator / workload reload controller
          │
          ▼
Kubernetes Secrets → Deployments / Jobs / Workers
```

A secret synchronization controller such as External Secrets Operator retrieves values from a dedicated secret manager and materializes Kubernetes `Secret` resources; it is not itself the secret authority or rotation orchestrator.

### 2.2 Core design principle: overlapping credentials

Do not rotate a shared password in place. Use a dual-identity (blue/green) credential pattern:

```text
old credential remains valid
        │
        ├── create/stage new credential
        ├── deploy consumers using new credential
        ├── verify health and actual dependency operations
        ├── wait/drain old live connections
        └── revoke old credential
```

This avoids the dangerous sequence where changing a password first causes old pods to fail before the rollout completes, leaving no known-good access path.

### 2.3 Credential classes

Not every secret rotates the same way:

| Credential type | Preferred mechanism | Rotation strategy | Typical consumer behavior |
|---|---|---|---|
| PostgreSQL application access | Dedicated non-owner login role; ideally dynamic DB credential | Blue/green DB role or short-lived generated login | Recreate/drain connection pools; restart workload if needed |
| MinIO/S3 access | Scoped service account per app/prefix | Create replacement key, cut over, revoke prior key | Refresh client config or roll deployment |
| Internal service-to-service auth | Workload identity / mTLS / JWT | Short-lived automatically renewed token/certificate | Reload or sidecar renews automatically |
| Third-party API key | Provider-managed key pair/version | Create secondary key, update consumers, verify, revoke old key | Versioned secret reference plus health check |
| Encryption/data key | KMS/HSM-managed envelope key | Rotate key versions, retain decrypt capability | New writes use current version; reads support old versions |
| Human account password | MFA + password manager + risk response | Event-driven, not routine automation | Interactive reset and session invalidation |

The long-term objective is to **reduce static passwords**, not simply rotate them more often. Prefer workload identity, dynamic secrets, mTLS certificates, short-lived access tokens, and scoped service accounts wherever the platform supports them.

## 3. Workflow identity

Follow the ADR-036 convention:

```text
security:credential-rotation:<credential-set-id>:<generation>
```

Examples:

```text
security:credential-rotation:cts-postgres-runtime:2026-09
security:credential-rotation:cts-minio-writer:2026-09
security:credential-rotation:nexus-s3-publisher:2026-09
```

One `CredentialRotationWorkflow` with provider-specific activity adapters. The workflow does not directly embed passwords in its inputs, history, signals, logs, activity return values, or error strings. Temporal workflow history is durable, so store only secret **references**, version identifiers, checksums/fingerprints where safe, credential metadata, and state transitions.

## 4. Task-queue topology

Rotation workflows are materially more privileged than ordinary media orchestration and must not run in the same worker process or task queue as CTS/TTS jobs.

| Task queue | Activities |
|---|---|
| `security-workflows` | Rotation workflow orchestration |
| `security-secret-provider` | Vault/secret-manager version operations |
| `security-kubernetes` | ExternalSecret/Secret sync and rollout observation |
| `security-database` | Database-role creation, grants, disable/revoke, verification |
| `security-object-storage` | MinIO service-account/key rotation and verification |

Use a dedicated Temporal namespace or narrowly privileged worker identity if rotation workflows can alter credentials.

## 5. Workflow structure

```text
CredentialRotationWorkflow v1
  ├── LoadRotationPolicy
  ├── AcquireRotationLock
  ├── InventoryConsumers
  ├── CreateSuccessorCredential
  ├── StoreCandidateSecretVersion
  ├── SynchronizeKubernetesSecret
  ├── RollOrReloadConsumers
  ├── VerifyConsumerHealth
  ├── VerifyRealDependencyOperation
  ├── AwaitGraceAndDrainPeriod
  ├── RevokePredecessorCredential
  ├── VerifyRevocation
  ├── WriteRotationEvidence
  └── NotifySecurityAndOwners
```

Each step is idempotent. Retrying "create successor" returns the same successor version, not an unbounded set of accounts/keys.

## 6. Secret-safe input and result contracts

### 6.1 Input envelope

Uses opaque references — never credential values:

```json
{
  "credential_set_id": "cts-postgres-runtime",
  "credential_class": "postgresql_login",
  "secret_ref": {
    "provider": "vault",
    "path": "platform/cts/postgres/runtime",
    "current_version": "v17"
  },
  "rotation_policy_id": "service-db-standard-v1",
  "consumer_selector": {
    "namespace": "cts",
    "workloads": ["cts-backend", "cts-watchdog"]
  },
  "strategy": "dual_login_role",
  "correlation_id": "corr_01J..."
}
```

### 6.2 Result envelope

References versions, never values:

```json
{
  "credential_set_id": "cts-postgres-runtime",
  "status": "completed",
  "previous_version": "v17",
  "active_version": "v18",
  "previous_identity": "cts_runtime_a",
  "active_identity": "cts_runtime_b",
  "verification": {
    "workload_ready": true,
    "database_connectivity": true,
    "read_write_probe": true,
    "old_credential_revoked": true
  },
  "correlation_id": "corr_01J..."
}
```

## 7. PostgreSQL pattern

### 7.1 Preferred: short-lived dynamic database users

If a Vault or equivalent secret broker is adopted, let it generate short-lived PostgreSQL credentials per workload/lease. The broker creates a temporary database login with narrowly scoped grants; workloads renew it while alive, and the broker revokes it at lease expiry.

```text
Pod authenticates with workload identity
  → secret broker issues a DB credential with a short TTL
  → application receives/renews credential
  → credential expires automatically if pod disappears
```

This eliminates most manual password rotation and sharply limits blast radius.

### 7.2 Pragmatic: blue/green login roles

For the current PostgreSQL/PgBouncer/Kubernetes setup, use two non-owner roles:

```text
cts_runtime_a
cts_runtime_b
```

Both belong to a capability role:

```sql
CREATE ROLE cts_runtime NOLOGIN;

GRANT CONNECT ON DATABASE mydatabase TO cts_runtime;
GRANT USAGE ON SCHEMA public TO cts_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cts_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cts_runtime;

GRANT cts_runtime TO cts_runtime_a;
GRANT cts_runtime TO cts_runtime_b;
```

The rotation workflow:

1. Determine active login identity from the current secret reference.
2. Select inactive identity.
3. Set a freshly generated password only for the inactive identity.
4. Write a new secret version referring to the inactive identity/password.
5. Update the workload-facing secret pointer.
6. Trigger a controlled rolling restart or supported hot reload.
7. Verify: pods ready, health endpoint passes, DB `SELECT` and a controlled write/read probe pass, PgBouncer sees authenticated connections from the new role.
8. Allow an explicit grace period so old pools/connections drain.
9. Disable prior login (`NOLOGIN`) or change/revoke its password.
10. Verify prior credentials no longer authenticate.
11. Record evidence and mark successor active.

Do not use `cortex_db_admin` as an application runtime account. It has broad privileges and has been used as a shared application connection identity. A rotation initiative is an opportunity to introduce least-privilege runtime roles, with migrations/admin work performed by a separate, more privileged identity.

### 7.3 PgBouncer considerations

With transaction pooling:

- New connections authenticate using the new credential after rollout.
- Existing server connections can remain usable during the grace period.
- Make application connection creation/retry resilient; credential rotation should not produce a permanent worker failure.
- Ensure rollout checks exercise an actual query and, where appropriate, an actual small write/read operation — not merely a TCP check.
- Drain or restart clients deliberately if they cache connections or DSNs.

## 8. Kubernetes secret delivery

Avoid direct plaintext Secrets in Git. Use this lifecycle:

```text
Secret authority stores versioned secret
      │
      ▼
External Secrets Operator syncs current approved version
      │
      ▼
Kubernetes Secret changes
      │
      ├── reload controller triggers rollout/reload
      └── application reads refreshed credential
```

For workload refresh, choose deliberately:

| Workload model | Rotation response |
|---|---|
| Reads env vars only at startup | Roll deployment/stateful set |
| Reads mounted secret files | Hot reload through file watch/SIGHUP where supported |
| Uses a connection pool | Build a new pool with the new credential; drain old pool |
| Long-running Temporal worker | Gracefully stop polling, drain current activities, restart with new secret |
| Scheduled job | New run picks up current secret version |

For critical deployments, use a rolling strategy such as `maxUnavailable: 0` where capacity permits, with readiness checks that validate the dependency — not merely that the process is running.

## 9. Rotation policy model

Make policies declarative and versioned:

```yaml
credentialSet: cts-postgres-runtime
type: postgresql_login
owner: cts-platform
rotation:
  mode: dual_login_role
  cadence: 30d
  gracePeriod: 30m
  maxRotationDuration: 45m
  requireApproval: false
  emergencyRotationOn:
    - secret_exposed
    - suspicious_authentication
    - role_owner_change
consumers:
  - namespace: cts
    workload: cts-backend
  - namespace: cts
    workload: cts-watchdog
verification:
  - workload_ready
  - database_read
  - database_write_read
  - old_credential_rejected
rollback:
  allowedBeforeOldCredentialRevocation: true
```

For particularly disruptive credentials, add a human approval step before revocation. For a confirmed exposure, use the emergency path: shorten grace period, revoke quickly, and trigger incident response.

## 10. Rotation scheduler and triggers

Use both scheduled and event-driven starts:

| Trigger | Example | Expected behavior |
|---|---|---|
| Time-based | Every 30–90 days for static service credentials | Start standard rotation workflow |
| Exposure | Secret detected in source, shell transcript, or CI logs | Start emergency rotation immediately |
| Personnel/access change | Admin or service owner changes | Rotate affected privileged credentials |
| Suspicious auth | Failed-login spike, unexpected source IP | Start or require approval for emergency rotation |
| Infrastructure change | Namespace migration, cluster rebuild, credential backend change | Rotate at cutover |
| Manual | Security owner requests | Validate policy and run documented workflow |

Use a Temporal Schedule for predictable cadence, but route every schedule invocation through the same deterministic workflow ID and policy evaluation logic. The workflow should still obtain a rotation lock to ensure concurrent or emergency starts do not collide.

## 11. Locks and concurrency

Credential rotation is a critical section. Use a distributed lock or a database row with lease semantics:

```text
credential_set_id = cts-postgres-runtime
rotation_generation = 18
state = rotating
lock_owner_workflow_id = security:credential-rotation:...
lock_expires_at = ...
```

Rules:

- Only one active rotation workflow per credential set.
- An emergency workflow can signal/escalate the active one or take over only after an explicit expired-lock policy.
- Consumer deployments must not independently rotate the same credential.
- The workflow must be idempotent at every step.

## 12. Failure, rollback, and revocation

Design a point of no return:

```text
Pre-revocation:
  New identity exists; old identity remains valid.
  Rollback = point consumers back to prior secret version.

Post-revocation:
  Old identity is disabled/deleted.
  Roll forward = repair new deployment/credential only.
```

Do not revoke until success evidence exists. If a rollout fails:

1. Keep old credential active.
2. Restore the prior secret version/pointer.
3. Roll back workload deployment or restart using previous version.
4. Verify actual application and dependency operations.
5. Leave a structured incident/evidence record.
6. Escalate for operator action.

For a confirmed secret exposure, the business may accept a shorter overlap period, but it should be an explicit emergency policy decision.

## 13. Verification standard

A successful rotation is not "the Secret exists." Require staged evidence:

```text
1. Candidate credential authenticates.
2. Candidate identity has least-privilege permissions.
3. Every consumer reports ready on the candidate version.
4. Each consumer performs an authenticated domain-relevant probe.
5. Existing work drains or is safely retried.
6. Old credential no longer authenticates after revocation.
7. Monitoring remains healthy through the grace window.
8. Rotation workflow writes immutable evidence.
```

For CTS, the probe should include:

- Connection through PgBouncer.
- `SELECT 1`.
- A safe transaction against a dedicated health/check table or a controlled test schema.
- Worker starts and can claim no real job or run a non-destructive queue-health probe.
- Object storage access for services that require both PostgreSQL and MinIO.

## 14. Observability and evidence

Standard metrics:

```text
credential_rotation_started_total{credential_set,type,trigger}
credential_rotation_completed_total{credential_set,status}
credential_rotation_duration_seconds{credential_set}
credential_rotation_step_failures_total{credential_set,step,error_code}
credential_rotation_secret_age_seconds{credential_set}
credential_rotation_overdue_total{credential_set}
credential_rotation_old_credential_still_active{credential_set}
```

Alert on:

- A credential approaching expiry without a successful successor.
- Rotation workflow stuck beyond its maximum duration.
- Failed verification after a secret sync/rollout.
- Old credential still authenticating after the revocation deadline.
- Consumer readiness failure after candidate cutover.
- Any emergency rotation triggered by credential exposure.

Keep audit records with secret **version IDs, role names, timestamps, policy version, workflow ID, run ID, consumer verification results, and operator approvals** — never the secret itself.

## 15. Integration with ADR-036

This ADR defines a platform workflow family under the ADR-036 standard:

```text
security.credential-rotation.v1
```

The workflow uses the standard `WorkflowEnvelope` with `contract_version`, `workflow_type`, and `idempotency_key` as defined in ADR-036. The result uses the standard `WorkflowResult` with the error taxonomy from ADR-036 for failure classification.

The rotation input and result are specialized envelope types (`RotationInput`, `RotationResult`) that extend the base contract with credential-specific fields while preserving the secret-safe property: no credential values appear in any serialized form.

## 16. Practical rollout path

### Phase 1: Make static secrets safer (current)

- Rotate the already exposed credentials immediately (manual, per runbook).
- Move all runtime secrets to Kubernetes Secrets referenced by `secretKeyRef` (CTS PR #4).
- Introduce non-owner, least-privilege runtime roles.
- Add secret scanning in pre-commit and CI.
- Add a credential inventory with owner, consumers, secret backend, last rotation, and next due date.

### Phase 2: Automate safe rotations

- Adopt a secret authority with versioned secret support.
- Deploy External Secrets Operator or equivalent synchronization.
- Implement the Temporal `CredentialRotationWorkflow`.
- Start with a low-risk MinIO scoped service account.
- Add verification and rollback evidence.
- Run in staging, then rotate one production-like credential with an operator approval gate.

### Phase 3: Reduce static credential use

- Move database access toward dynamic or dual-role credentials.
- Replace internal API keys with workload identity or short-lived JWT/mTLS authentication.
- Use certificates and automatic renewal where possible.
- Treat password rotation as an exception path for remaining legacy dependencies.

## 17. Recommended first automated rotation

1. **CTS MinIO scoped service account rotation** — lowest risk, proves the full workflow without touching the database path.
2. **CTS PostgreSQL blue/green runtime roles** — second, after separating runtime privileges from `cortex_db_admin`.
3. **Dynamic database credentials** — later, if Vault or a compatible secret broker is adopted.

That sequence proves the entire secure workflow — generate, stage, synchronize, roll, verify, revoke, audit — without putting the main CTS database path at risk first.

## 18. Acceptance criteria

ADR-037 is **adopted** when:

1. One credential set has been rotated end-to-end through the `CredentialRotationWorkflow`.
2. The rotation produced immutable evidence with version IDs, verification results, and timestamps.
3. The old credential was verified as revoked.
4. All consumers passed their domain-relevant health probes on the new credential.
5. No credential value appeared in workflow history, logs, metrics, or audit records.
6. The rotation survived a simulated consumer failure with successful rollback.
7. An emergency rotation trigger was tested and completed within the emergency grace period.

## 19. References

- ADR-032: Federated Governance & Multi-Plane Evidence Architecture
- ADR-036: Temporal Integration Standard — Cross-App Durable Orchestration
- [Temporal Schedules](https://docs.temporal.io/schedules)
- [External Secrets Operator](https://external-secrets.io/)
- [HashiCorp Vault Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- Incident: 2026-09-05 Credential Exposure Remediation

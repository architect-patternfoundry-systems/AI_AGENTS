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

## 16. Ownership model

A single "Owner" column is insufficient. Credential rotation involves three distinct roles with different responsibilities. Making these explicit prevents the quiet failure mode where "operator rotates password" becomes a permanent, undocumented operating model.

### 16.1 Three-role model

| Role | Responsibility | Human or platform? |
|---|---|---|
| **Credential owner** | Defines business purpose, allowed consumers, risk tier, and rotation policy | A named team/service owner; accountable but not performing rotations |
| **Rotation executor** | Generates/stages/cuts over/revokes credentials and collects evidence | `CredentialRotationWorkflow` plus provider-specific workers |
| **Exception approver** | Approves only policy-defined high-risk steps or resolves failed rotations | Human only when required by policy or incident severity |

### 16.2 Example assignments

| Credential set | Credential owner | Rotation executor | Exception approver |
|---|---|---|---|
| `cts-postgres-runtime` | CTS platform owner | `CredentialRotationWorkflow` | Database/platform approver for first enrollment or emergency revocation |
| `cts-minio-writer` | CTS platform owner | `CredentialRotationWorkflow` | Security approver only if policy requires |
| `nexus-s3-publisher` | Nexus owner | `CredentialRotationWorkflow` | Nexus/security approver for destructive scope changes |

### 16.3 Why a one-time operator step exists

The first rotation is special because automation cannot safely rotate a secret it does not yet control. The platform currently has these bootstrapping gaps:

1. The exposed credentials must be invalidated immediately.
2. Kubernetes Secrets need to be seeded with post-rotation values.
3. Secret-manager authority may not yet be deployed or trusted by workloads.
4. The `CredentialRotationWorkflow` worker and provider adapters are not implemented yet.
5. PostgreSQL runtime identities need to be split away from an administrative connection identity.
6. MinIO needs a scoped service-account model or a similar replacement identity.
7. The workflow needs a credential with authority to create/revoke successor credentials — but that authority itself must be carefully scoped and protected.

The right approach is a **one-time bootstrap rotation**, followed immediately by enrolling the new credential set into automated management. The existing exposed credential must not remain active until full automation exists.

### 16.4 Two kinds of manual work

**Manual once: establish trust.** A human must initially commission the control plane:
- Deploy/configure secret authority.
- Create scoped rotation identities.
- Seed the initial managed secret version.
- Give the rotation worker narrowly scoped capability to create/revoke successors.
- Enroll workloads and validate rollout/reload behavior.
- Validate that evidence does not leak secret material.
- Approve the policy for first automatic rotation.

This is infrastructure commissioning, not routine credential operation.

**Automatic thereafter: rotate normally.** Once enrolled:
- Temporal Schedule triggers rotation.
- Workflow obtains rotation lock.
- Provider adapter creates successor credentials.
- Secret authority stores a new version.
- External Secrets syncs / Kubernetes rollout applies it.
- Verification activities test real workload behavior.
- Workflow drains/revokes predecessor.
- Evidence is written.
- Owners receive an outcome notification.

No person needs to copy a password, type a password, create a Secret manually, or restart pods manually during a normal rotation.

### 16.5 RACI for the mature state

| Activity | Platform security | App owner | Rotation workflow | Secret provider | Human operator |
|---|---|---|---|---|---|
| Define rotation policy | A/R | C | I | I | I |
| Register credential/consumers | A | R | I | I | C |
| Generate successor | I | I | R | Executes | I |
| Deliver updated secret | I | I | R | Stores/version-controls | I |
| Roll consumers | I | I | R | I | I |
| Verify cutover | I | I | R | I | I |
| Revoke predecessor | A | I | R | Executes | I |
| Review evidence | A | C | Produces | I | I |
| Handle failed rotation | A | C | Detects/escalates | C | R only by exception |
| Emergency exposure event | A | C | R for policy-approved path | Executes | R only if automation cannot safely proceed |

The human operator is **not on the normal-path execution flow**. They are an exception handler.

## 17. Enrollment lifecycle

A credential set moves through a defined lifecycle from discovery to automated management. The lifecycle state determines whether human intervention is expected, allowed, or prohibited.

### 17.1 Lifecycle states

```text
discovered
  → bootstrap_required
  → enrolled
  → rotation_ready
  → automatically_managed
  → rotation_degraded
  → emergency_rotation
  → retired
```

| State | Meaning | Rotation behavior |
|---|---|---|
| `discovered` | Credential exists but has not been inventoried | No automated action |
| `bootstrap_required` | Credential is known, but secret authority/workload integration is not ready | One-time human-assisted remediation |
| `enrolled` | Secret is stored in approved authority and consumers are mapped | Validation only |
| `rotation_ready` | Successor creation, deployment cutover, verification, rollback, and revocation paths have passed a dry run | Scheduled workflow may be enabled |
| `automatically_managed` | Normal state | Scheduled and event-driven rotations are workflow-owned |
| `rotation_degraded` | Automation cannot complete safely | Preserve current credential; alert and open exception workflow |
| `emergency_rotation` | Exposure or compromise trigger | Automated fast path; human approval only if policy requires |
| `retired` | Credential set no longer in use | Revoke, delete secrets, archive evidence |

### 17.2 Transition plan

A credential set listed as human-assisted must have an explicit transition plan. "Operator" is a **transition executor**, not the permanent owner of a recurring task.

| Item | Current executor | Target executor | Transition criterion |
|---|---|---|---|
| Rotate exposed PostgreSQL credential | Human-assisted bootstrap | `CredentialRotationWorkflow` | Runtime roles, secret authority, rollout verification, and revoke adapter are enrolled |
| Rotate MinIO root/service credential | Human-assisted bootstrap | `CredentialRotationWorkflow` | Scoped service account and MinIO provider adapter exist |
| Create workload-facing Kubernetes secret | Bootstrap deployment action | External Secrets Operator or equivalent | Secret authority source and sync policy are configured |
| Restart/reload consumers | Bootstrap deployment action | Rotation workflow + rollout adapter | Workload health and dependency probes are automated |
| Verify old secret invalidation | Human oversight initially | Rotation verification activity | Old credential rejection probe succeeds |
| Recurring rotation | Not yet enabled | Temporal Schedule → rotation workflow | Credential set reaches `rotation_ready` |

### 17.3 Automation tracking field

Each credential set carries an automation tracking record that makes the human burden visible, temporary, measurable, and removable:

```yaml
automation:
  lifecycle_state: bootstrap_required
  target_state: automatically_managed
  enrollment_deadline: 2026-10-01
  current_exception: "exposed static password; secret authority not yet enrolled"
  manual_steps_remaining:
    - rotate current exposed credential
    - provision scoped rotation identity
    - seed first managed secret version
    - validate end-to-end dry run
```

### 17.4 Bootstrap boundary statement

Bootstrap rotations are a temporary remediation state, not an operating model. A credential set may be listed as human-assisted only while it is in `bootstrap_required` or `rotation_ready` enrollment. It must have:
- a named transition plan,
- an automation target,
- an enrollment deadline,
- an owner accountable for making it `automatically_managed`.

Routine scheduled rotations for `automatically_managed` credential sets must be performed by `CredentialRotationWorkflow` without human handling of secret values.

## 18. Practical rollout path

### Phase 1: Make static secrets safer (current)

- Rotate the already exposed credentials immediately (manual bootstrap, per runbook).
- Move all runtime secrets to Kubernetes Secrets referenced by `secretKeyRef` (CTS PR #4).
- Introduce non-owner, least-privilege runtime roles.
- Add secret scanning in pre-commit and CI.
- Add a credential inventory with owner, consumers, secret backend, last rotation, next due date, and lifecycle state.

### Phase 2: Automate safe rotations

- Adopt a secret authority with versioned secret support.
- Deploy External Secrets Operator or equivalent synchronization.
- Implement the Temporal `CredentialRotationWorkflow`.
- Start with a low-risk MinIO scoped service account.
- Add verification and rollback evidence.
- Run in staging, then rotate one production-like credential with an operator approval gate.
- Move credential sets from `bootstrap_required` → `enrolled` → `rotation_ready` → `automatically_managed`.

### Phase 3: Reduce static credential use

- Move database access toward dynamic or dual-role credentials.
- Replace internal API keys with workload identity or short-lived JWT/mTLS authentication.
- Use certificates and automatic renewal where possible.
- Treat password rotation as an exception path for remaining legacy dependencies.

## 19. Recommended first automated rotation

1. **CTS MinIO scoped service account rotation** — lowest risk, proves the full workflow without touching the database path.
2. **CTS PostgreSQL blue/green runtime roles** — second, after separating runtime privileges from `cortex_db_admin`.
3. **Dynamic database credentials** — later, if Vault or a compatible secret broker is adopted.

That sequence proves the entire secure workflow — generate, stage, synchronize, roll, verify, revoke, audit — without putting the main CTS database path at risk first.

## 20. Acceptance criteria

ADR-037 is **adopted** when:

1. One credential set has been rotated end-to-end through the `CredentialRotationWorkflow`.
2. The rotation produced immutable evidence with version IDs, verification results, and timestamps.
3. The old credential was verified as revoked.
4. All consumers passed their domain-relevant health probes on the new credential.
5. No credential value appeared in workflow history, logs, metrics, or audit records.
6. The rotation survived a simulated consumer failure with successful rollback.
7. An emergency rotation trigger was tested and completed within the emergency grace period.

### 20.1 Operator-free rotation criterion

For an `automatically_managed` credential set, a normal scheduled rotation must complete without a human accessing, seeing, copying, generating, transporting, or manually applying the secret value.

Measurable acceptance:

```text
Given a scheduled rotation of an enrolled non-production credential:
  - no human shell command is required;
  - no plaintext secret appears in workflow input, logs, activity result,
    Kubernetes manifest, Git diff, or ticket;
  - a successor is generated and stored only in the secret authority;
  - consumers are updated and verified;
  - predecessor is revoked;
  - workflow evidence proves success;
  - a human receives only a notification/result, not the secret.
```

This is the definition of done for the steady-state operating model.

## 21. References

- ADR-032: Federated Governance & Multi-Plane Evidence Architecture
- ADR-036: Temporal Integration Standard — Cross-App Durable Orchestration
- [Temporal Schedules](https://docs.temporal.io/schedules)
- [External Secrets Operator](https://external-secrets.io/)
- [HashiCorp Vault Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- Incident: 2026-09-05 Credential Exposure Remediation

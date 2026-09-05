# ADR-038: Credential Discovery, Inventory, and Enrollment Standard

**Status:** Proposed
**Date:** 2026-09-05
**Author:** Platform Team
**Category:** Security
**Related:** ADR-032 (Federated Governance), ADR-036 (Temporal Integration Standard), ADR-037 (Credential Rotation Lifecycle Workflow)

---

## 1. Context

ADR-037 defined the credential rotation lifecycle and the `CredentialRotationWorkflow`. But rotation is only the execution half of the problem. Before a credential can be rotated automatically, the platform must:

1. Discover that the credential exists.
2. Identify where it is used and who owns it.
3. Assess whether it can be safely automated.
4. Enroll it in a secret authority with consumer mapping.
5. Verify the full rotation path before enabling schedules.

This is currently done ad hoc — a human searches repositories, inspects manifests, and maintains a mental model of which credentials exist. That does not scale and it does not self-improve.

ADR-038 defines the **Credential Discovery, Inventory, and Enrollment Standard**: the system that makes ADR-037's lifecycle model operate as a control plane rather than documentation.

## 2. Decision

Define four separated capabilities with distinct privilege boundaries:

| Capability | Purpose | Authority |
|---|---|---|
| **Credential Discovery Controller** | Finds references, usage, and exposure signals; never needs to reveal or persist secret values | Read-only discovery permissions |
| **Credential Inventory Service** | Maintains canonical metadata, ownership, risk, lifecycle, and evidence | Metadata database |
| **Credential Enrollment Workflow** | Moves one credential set into managed rotation | Controlled write permissions through Temporal |
| **Credential Rotation Workflow** | Performs routine scheduled/event-driven rotation after enrollment | Privileged, narrow provider adapters |

This separation matters because discovery is broad and read-oriented, while rotation is privileged and should be tightly constrained. A scanner that can list every Secret should not automatically receive database-admin or MinIO-admin capability.

## 3. Governing rule

> Every discovered non-human credential is represented as a redacted `CredentialSet` inventory record, assigned an accountable owner, assessed for automation capability, and tracked through a lifecycle to either `automatically_managed`, explicitly excepted with expiry, or retired.

## 4. Credential inventory record

The inventory contains **metadata and fingerprints**, never plaintext secret material.

```yaml
credential_set_id: cts-postgres-runtime
display_name: CTS PostgreSQL runtime access
credential_class: postgresql_login
environment: dev
lifecycle_state: bootstrap_required

owner:
  team: cts-platform
  service: attunement-weaver
  escalation_group: platform-security

authority:
  provider: kubernetes_secret
  namespace: cts
  secret_name: cts-db-secret
  key_names:
    - uri
    - password
  external_secret_ref: null

consumers:
  - kind: Deployment
    namespace: cts
    name: cts-backend
    container: cts-backend
    env_var: POSTGRES_DSN
  - kind: Deployment
    namespace: cts
    name: cts-watchdog

risk:
  tier: high
  has_admin_privileges: true
  exposure_status: exposed_rotated_pending_enrollment
  last_scanned_at: "2026-09-05T..."
  secret_fingerprint: "hmac-sha256:..."
  source_findings:
    - scanner: git-history
      location_ref: "repo:...:commit:..."
      severity: critical

rotation:
  target_strategy: dual_login_role
  current_mode: static_unmanaged
  target_mode: automatically_managed
  cadence_days: 30
  next_rotation_due_at: null
  enrollment_deadline: "2026-10-01T00:00:00Z"

capabilities:
  successor_creation: false
  dual_credential_supported: true
  consumer_reload_supported: rolling_restart
  positive_probe_supported: true
  predecessor_revocation_supported: false

evidence_refs:
  - "s3://security-evidence/credential-inventory/..."
```

### 4.1 Fingerprint security

`secret_fingerprint` must be created with a platform-held HMAC key, not a raw SHA-256 of the secret. Raw hashes of low-entropy passwords or known key formats can become an offline guessing target. The HMAC key is held by the inventory service and never exposed to discovery agents, scanners, or workflow history.

## 5. Discovery sources

Multiple scanners produce observations into the same inventory. No one scanner is enough.

### 5.1 Kubernetes credential-reference discovery

Scan Kubernetes resources for **references**, not values:

- `Secret` metadata: namespace, name, key names, creation time, annotations, type.
- `Deployment`, `StatefulSet`, `DaemonSet`, `Job`, `CronJob`:
  - `env.valueFrom.secretKeyRef`
  - `envFrom.secretRef`
  - secret-backed volumes
  - projected volumes
  - `imagePullSecrets`
  - service-account assignments.
- `ExternalSecret`, `SecretStore`, `ClusterSecretStore`, CSI Secret Store resources.
- Workload ownership, labels, annotations, container/env-var mapping.
- RBAC bindings that grant Secret-read capability.

This answers: Which workloads consume which secret? Which secrets are unmanaged Kubernetes-native Secrets? Which secrets are already externally sourced? Which workloads will require restart vs file reload?

### 5.2 Git and artifact discovery

Scan Git working trees and commit history, CI/CD definitions, deployment templates, Helm values, Kustomize overlays, Terraform/Pulumi, Docker Compose, `.env` examples, ADRs, runbooks, incident reports, generated logs, copied shell transcripts, script defaults, connection strings, test fixtures, `alembic.ini`.

Use Gitleaks or similar for pattern detection, but ingest only a redacted finding:

```json
{
  "finding_id": "finding_...",
  "detector": "gitleaks",
  "rule_id": "postgres-dsn",
  "location_ref": "git:repo/path@commit:line",
  "confidence": "high",
  "secret_fingerprint": "hmac-sha256:...",
  "plaintext_retained": false
}
```

Do **not** copy matched secret content into the inventory, Temporal inputs, tickets, PR comments, or alert payloads.

### 5.3 Runtime configuration discovery

Look at live workload configuration metadata:

- Environment variable names — not values.
- Mounted secret file names and mount paths.
- OpenTelemetry resource attributes / config source annotations.
- ConfigMaps that point to secret locations.
- Application health/config endpoints that expose only secret version IDs or source references.
- Pod labels identifying app, environment, component, and owner.

Add an application convention:

```text
security.platform.io/credential-set.<logical-name>: <credential-set-id>
security.platform.io/secret-source: external|kubernetes|vault|unknown
security.platform.io/reload-mode: restart|sighup|file-watch|dynamic
```

This makes future inventory nearly automatic. A scanner should never need to infer every dependency from a DSN string.

### 5.4 Provider-side identity discovery

Inventory actual identities in the systems that validate credentials:

| Provider | Discover |
|---|---|
| PostgreSQL | Login roles, memberships, role age, `VALID UNTIL`, ownership, broad privileges, connection/application usage |
| MinIO | Users, service accounts, policies, key age, bucket/prefix scope |
| GitHub/GitLab | Deploy keys, PATs where visible, GitHub Apps, Actions secrets metadata |
| Cloud providers | IAM access keys, service principals, secret versions, role bindings |
| Vault/OpenBao | Secret paths, engines, lease/TTL data, policies, entities |
| Kubernetes | Service accounts, token automount behavior, RBAC scope |
| External APIs | Registered key identifiers, expiry dates, usage timestamps where provider APIs support it |

This is how orphaned credentials are identified — identities that still exist but have no mapped consumer or owner.

### 5.5 Network and authentication telemetry

Where available, correlate actual use:

- PostgreSQL connection logs or `pg_stat_activity`: login role, application name, client source, last seen.
- MinIO audit logs: access key ID, bucket/prefix, last seen.
- Reverse-proxy/API gateway logs: API key ID/token subject, endpoint use, last seen.
- Kubernetes audit logs: Secret reads and service-account use.
- CI audit logs: which pipeline/runner accessed a secret.

This makes inventory more than a source-code catalogue. It tells you whether a credential is active, stale, orphaned, or shared.

## 6. Enrollment workflow

Once discovery produces a candidate, start a dedicated workflow:

```text
security:credential-enrollment:<credential-set-id>:<generation>
```

This is distinct from rotation:

```text
CredentialEnrollmentWorkflow v1
  ├── ConsolidateDiscoveryEvidence
  ├── ResolveCredentialSetIdentity
  ├── InferAndConfirmConsumers
  ├── AssignOrEscalateOwner
  ├── AssessRiskAndPrivilege
  ├── AssessRotationCapabilities
  ├── SelectTargetStrategy
  ├── GenerateEnrollmentPlan
  ├── AwaitApproval, if required
  ├── CreateScopedSuccessorIdentity
  ├── SeedExternalSecretAuthority
  ├── ConfigureSecretSynchronization
  ├── UpdateConsumerReferences
  ├── ValidateCutoverAndRollback
  ├── RegisterRotationPolicy
  ├── MarkRotationReady
  └── ScheduleFirstManagedRotation
```

### 6.1 Observe-only mode

The workflow must support an **observe-only mode**. In this mode it creates an inventory record and an enrollment plan, but makes no changes. That is how the environment is safely inventoried before granting the workflow broad authority.

### 6.2 Enrollment steps

| Step | Purpose | Observe-only? |
|---|---|---|
| ConsolidateDiscoveryEvidence | Merge findings from all scanners | Yes |
| ResolveCredentialSetIdentity | Determine if this is a new or known credential set | Yes |
| InferAndConfirmConsumers | Map workloads to credential references | Yes |
| AssignOrEscalateOwner | Match to team/service or flag as unowned | Yes |
| AssessRiskAndPrivilege | Determine risk tier and privilege scope | Yes |
| AssessRotationCapabilities | Check successor/overlap/delivery/probe/revocation | Yes |
| SelectTargetStrategy | Choose dual_login_role, dynamic, key_version, etc. | Yes |
| GenerateEnrollmentPlan | Produce structured plan with deadlines | Yes |
| AwaitApproval | Human approval for high-risk enrollment | Yes (approval gate) |
| CreateScopedSuccessorIdentity | Create inactive identity in provider | No |
| SeedExternalSecretAuthority | Store successor in Vault/ESO | No |
| ConfigureSecretSynchronization | Set up ExternalSecret/SecretStore | No |
| UpdateConsumerReferences | Point workloads to new secret | No |
| ValidateCutoverAndRollback | Verify and test rollback | No |
| RegisterRotationPolicy | Create policy in rotation scheduler | No |
| MarkRotationReady | Transition lifecycle state | No |
| ScheduleFirstManagedRotation | Enable Temporal Schedule | No |

## 7. Capability assessment matrix

A powerful enrollment helper does not merely say "found secret." It determines whether rotation is automatable.

| Capability | Example evidence | What it determines |
|---|---|---|
| `successor_creation` | DB role admin adapter can create inactive login; MinIO API can create SA | Can automate successor creation |
| `overlap_support` | Two database roles or dual API keys are supported | Can cut over without downtime |
| `secret_authority` | Vault/OpenBao/external provider writable path exists | Can store versioned successor safely |
| `delivery` | ESO/CSI or supported secret sync exists | Can update Kubernetes consumers automatically |
| `consumer_reload` | Deployment rolling restart, file watch, SIGHUP, pool reload | Can apply successor |
| `positive_probe` | Read/write DB probe; object put/get; API token request | Can verify candidate works |
| `predecessor_revocation` | Disable old role/key through provider API | Can complete rotation safely |
| `audit_observability` | Provider usage logs identify active key/role | Can prove predecessor is drained/revoked |

### 7.1 Readiness calculation

```text
rotation_ready =
  successor_creation
  AND overlap_support
  AND secret_authority
  AND delivery
  AND consumer_reload
  AND positive_probe
  AND predecessor_revocation
```

Anything missing becomes a structured enrollment task, not tribal knowledge.

## 8. Human burden reduction

The objective is not zero human involvement at the beginning. It is **zero secret handling and zero repetitive execution** once a credential is enrolled.

Use an "exception inbox," not an operator runbook:

```text
Discovery finds candidate
  → system proposes inventory record and plan
  → owner only resolves ambiguity / approves scope
  → workflow performs enrollment
  → policy schedules rotation
  → human receives evidence notification
```

The human should be asked questions only where automation cannot safely infer intent:

- "Is this credential still needed?"
- "Who owns this unknown PostgreSQL role?"
- "May this broad shared account be split into per-app runtime identities?"
- "Is this external API key allowed to be replaced with a new one?"
- "Is a 30-minute overlap acceptable?"
- "Should this be emergency-rotated now due to confirmed exposure?"

They should **not** be asked to copy a password into `kubectl`, edit a DSN, restart pods, or verify a credential manually during normal enrollment.

## 9. Kubernetes-native interface

A CRD or Git-managed custom resource provides a declarative onboarding interface:

```yaml
apiVersion: security.patternfoundry.dev/v1alpha1
kind: CredentialSet
metadata:
  name: cts-postgres-runtime
  namespace: cts
spec:
  owner:
    team: cts-platform
  credentialClass: postgresql_login
  provider:
    type: postgresql
    instanceRef: infra-data-postgres
  consumers:
    selector:
      matchLabels:
        app: cts-backend
  delivery:
    type: external-secret
    secretStoreRef: platform-vault
    targetSecretName: cts-db-secret
  rotation:
    strategy: dual_login_role
    cadence: 30d
    gracePeriod: 30m
    maxRetries: 3
  verification:
    - workload_ready
    - database_read
    - database_write_read
    - old_credential_rejected
  enrollment:
    mode: observe_only
    targetState: automatically_managed
```

A controller reconciles this resource:

- Discovers current state.
- Updates inventory status.
- Creates a Temporal enrollment workflow when appropriate.
- Stores status fields without leaking values.
- Starts rotation on schedule after `automatically_managed`.

This gives a repeatable onboarding interface for both existing unmanaged credentials and new credentials introduced by future apps.

## 10. Platform components

| Component | Implementation shape | Privilege |
|---|---|---|
| `credential-discovery-agent` | Read-only Kubernetes controller/CronJob plus provider scanners | Read metadata, not values where possible |
| `credential-inventory-api` | PostgreSQL-backed service/table, optionally exposed in security UI | Stores metadata and evidence refs |
| `credential-enrollment-worker` | Temporal worker on `security-workflows` | Controlled enrollment adapters |
| `credential-rotation-worker` | Temporal worker with provider activity queues | Privileged per provider, least privilege |
| `secret-authority` | Vault/OpenBao/cloud manager | Holds actual secret values and versions |
| `secret-sync` | External Secrets Operator / CSI driver | Synchronizes approved versions to workloads |
| `credential-policy-controller` | CRD controller or GitOps evaluator | Schedules/blocks rotation based on state/policy |
| `security-dashboard` | UI/read model | Shows posture, ownership gaps, deadlines, evidence |

Keep discovery and rotation workers separate. A scanner that can list every Secret should not automatically receive database-admin or MinIO-admin capability.

## 11. Inventory health metrics

```text
credential_inventory_total{state,credential_class,environment}
credential_inventory_unowned_total{credential_class}
credential_inventory_unmanaged_total{credential_class}
credential_enrollment_started_total{credential_class}
credential_enrollment_completed_total{status}
credential_enrollment_blocked_total{blocker}
credential_enrollment_deadline_overdue_total
credential_rotation_ready_total
credential_rotation_automatically_managed_total
credential_orphaned_total{provider}
credential_shared_across_apps_total
credential_exposure_findings_total{source,severity}
```

### 11.1 Operational views

- Credentials discovered but not owned.
- Credentials owned but unmanaged.
- Credentials in bootstrap longer than 30 days.
- High-risk/admin credentials with no rotation plan.
- Credentials referenced by workloads but absent from the secret authority.
- Provider identities that have not been used in 30/60/90 days.
- Secrets that appear in Git history or incident artifacts.
- Scheduled rotations due or overdue.

## 12. Integration with ADR-036 and ADR-037

### 12.1 ADR-036 alignment

The enrollment workflow uses the standard `WorkflowEnvelope` with `contract_version`, `workflow_type`, and `idempotency_key`. The workflow type is:

```text
security.credential-enrollment.v1
```

It runs on the `security-workflows` task queue defined in ADR-037 section 4. Provider-specific activities use the security sub-queues (`security-database`, `security-object-storage`, `security-kubernetes`, `security-secret-provider`).

### 12.2 ADR-037 alignment

The enrollment workflow transitions a credential set through the lifecycle states defined in ADR-037 section 17:

```text
discovered → bootstrap_required → enrolled → rotation_ready → automatically_managed
```

The `AutomationTracking` record from ADR-037 is updated at each transition. The enrollment workflow is the mechanism that moves a credential set from `bootstrap_required` to `rotation_ready`. The rotation workflow (ADR-037) takes over from `rotation_ready` to `automatically_managed` and beyond.

### 12.3 Separation from rotation

Enrollment and rotation are distinct workflows with distinct identities:

| Workflow | Identity pattern | Purpose |
|---|---|---|
| `CredentialEnrollmentWorkflow` | `security:credential-enrollment:<set>:<gen>` | One-time: move to managed state |
| `CredentialRotationWorkflow` | `security:credential-rotation:<set>:<gen>` | Recurring: rotate credentials on schedule |

Enrollment may create the first successor identity and seed the secret authority. Rotation uses the established authority to create subsequent successors. Enrollment is run once per credential set (or again if the set needs re-enrollment after a major change). Rotation runs on a schedule.

## 13. Phased implementation

### Phase 1: Inventory-only

Build `CredentialDiscoveryWorkflow` or a scheduled discovery job that:

- Scans Kubernetes Secret references and workload consumers.
- Scans known repositories and CI/deployment configuration.
- Lists PostgreSQL roles and MinIO access identities.
- Produces redacted findings and inventory records.
- Does not change infrastructure or retrieve/persist plaintext values.

This immediately replaces ad hoc searching with a repeatable posture report.

### Phase 2: Enrollment planning

Add:

- Capability assessment.
- Deduplication/correlation across source, runtime, and provider findings.
- Owner assignment and escalation.
- Generated enrollment plans.
- `observe_only` `CredentialSet` resources.
- Deadline/SLA tracking via the `AutomationTracking` model.

### Phase 3: Low-risk automatic enrollment

Start with MinIO scoped service accounts:

- Generate a scoped successor.
- Store it in the secret authority.
- Sync through ESO.
- Restart/reload one canary workload.
- Verify prefix-scoped object put/get.
- Roll back safely before old-key revocation.
- Promote to `automatically_managed`.

### Phase 4: Database enrollment

Add blue/green PostgreSQL runtime roles, connection-pool cutover, read/write verification, grace period, and predecessor rejection verification.

## 14. Acceptance criteria

ADR-038 is **adopted** when:

1. A discovery scan produces inventory records for all known credential sets across the platform without retaining plaintext values.
2. Each inventory record has an assigned owner, risk tier, and lifecycle state.
3. The capability assessment matrix correctly identifies which credential sets are `rotation_ready` and which have blockers.
4. At least one credential set has been enrolled end-to-end through `CredentialEnrollmentWorkflow` from `bootstrap_required` to `rotation_ready`.
5. The enrollment workflow in observe-only mode produces a plan without making infrastructure changes.
6. Inventory health metrics are exposed and alert on unowned, unmanaged, or overdue credentials.
7. No plaintext secret value appears in the inventory database, workflow history, logs, metrics, or CRD status fields.

## 15. References

- ADR-032: Federated Governance & Multi-Plane Evidence Architecture
- ADR-036: Temporal Integration Standard — Cross-App Durable Orchestration
- ADR-037: Credential Rotation Lifecycle Workflow
- [External Secrets Operator](https://external-secrets.io/)
- [HashiCorp Vault Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [Gitleaks](https://github.com/gitleaks/gitleaks)
- [Kubernetes Secret Discovery Best Practices](https://kubernetes.io/docs/concepts/configuration/secret/)

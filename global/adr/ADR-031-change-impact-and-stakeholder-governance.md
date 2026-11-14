# ADR-031: Change Impact Analysis, Stakeholder Resolution, and RASCI Governance Framework

## Status
Accepted (Governance Standard)

## Context
Production configuration and infrastructure changes (such as database connection pool security cutovers, ingress migrations, network policies, and storage topology shifts) affect multiple interdependent workloads, operational teams, and downstream service owners across sovereign repositories and namespaces.

Historically, changes often relied on informal manual notifications, static runbooks, or ad hoc approver lists. This approach creates critical operational risks:
1. **Unidentified blast radius:** Downstream consumers depending on or connected to a mutating component may experience unexpected reconnections or performance degradation without advance notice.
2. **Approval fatigue vs. safety bottlenecks:** Requiring everyone to approve creates organizational gridlock, while failing to distinguish between Accountable authorities, Responsible operators, Consulted dependencies, and Informed stakeholders leads to missing critical approvals or noisy unread alerts.
3. **Ambiguous authorization context:** Approvers often receive an opaque plan hash or raw technical manifest without a human-readable decision brief, clear expected behavior envelope, or explicit acknowledgement of operational risk.
4. **Weak evidence linkage:** Audit logs often separate the initial change request from the CMDB dependency snapshot, the human authorization decision, runtime preflight verification, and post-cutover health telemetry.

## Decision

We adopt the **Attested Change Impact and RASCI Stakeholder Governance Framework** for all security-sensitive and production infrastructure changes.

### 1. The Five Pillars of Change Authorization

Every change authorization is represented as a cryptographically signed, immutable **Change Plan** connecting five pillars of evidence:

$$\text{Change Authorization} = \text{Source Provenance} \land \text{CI Impact Graph} \land \text{Risk \& Expected Behavior Envelope} \land \text{RASCI Obligations} \land \text{Attested Approvals}$$

1. **Source Provenance:** 40-character Git commit SHA, immutable container image index digests, signed release manifests, and verified PR reviews.
2. **CI Impact Graph:** Deterministic traversal of CMDB configuration items (CIs) and relationships (`connects_to`, `depends_on`, `consumes`, `operated_by`, `owned_by`, `on_call_for`).
3. **Risk & Expected Behavior Envelope:** Typed declaration of planned maintenance duration, maximum allowed downtime, permissible error signatures (e.g. transient connection retries), and strictly prohibited outcomes (e.g. persistent auth failures or data corruption).
4. **RASCI Obligations:** Versioned policy assigning exact roles:
   * **Responsible (R):** Operator planning, initiating, verifying, and rolling back the change.
   * **Accountable (A):** Delegated authority owning the decision, approving the immutable plan, and accepting residual risk.
   * **Supporting (S):** Platform, database, and infrastructure teams providing operational readiness.
   * **Consulted (C):** Owners of directly impacted Tier 0/Tier 1 services who confirm business constraints and maintenance windows.
   * **Informed (I):** On-call groups, product owners, and downstream observers receiving operational notices.
5. **Attested Approvals:** Asymmetric Ed25519-signed authorization assertions (OIDC + step-up MFA), GitHub Protected Environment peer deployment review, and in-workflow Temporal atomic nonce consumption with live anchor revalidation.

---

### 2. CMDB Configuration Item (CI) & Relationship Schema

All CIs and relationships are modelled as typed, time-bounded, attested entities:

* **Configuration Item Attributes:**
  * `ci_id`: Stable immutable identifier (e.g. `ci:pgbouncer:infra-data`).
  * `ci_type`: `service | deployment | database | queue | api | cronjob | datastore`.
  * `name`: Human-readable display name.
  * `namespace` / `environment`: Runtime scope (`infra-data`, `toneroot`, `production`, etc.).
  * `owner_group_id`: Accountable service group (`A`).
  * `operator_group_id`: Responsible operational group (`R`).
  * `security_owner_group_id`: Security authority.
  * `business_owner_group_id`: Product or business owner.
  * `criticality`: `tier_0 | tier_1 | tier_2 | tier_3`.
  * `data_classification`: `public | internal | confidential | regulated`.
  * `notification_policy_id`: Notification routing reference.
  * `evidence_version`: Attested snapshot hash.

* **Relationship Attributes:**
  * `relationship_id`: Unique identifier.
  * `source_ci_id` $\rightarrow$ `relationship_type` $\rightarrow$ `target_ci_id`.
  * `relationship_type`: `connects_to | depends_on | consumes | hosts | operated_by | owned_by | on_call_for | security_authority_for | data_owner_for`.
  * `confidence`: `attested | inferred | unverified`.
  * `evidence_ref`: Log, manifest, or network policy reference confirming the link.
  * `last_attested_at`: ISO8601 timestamp.

---

### 3. Deterministic Stakeholder Resolution Algorithm

The Stakeholder Resolver takes `(target_cis, environment, change_class, expected_behavior, cmdb_snapshot)` and computes:
1. **Impact Set:** Traverses inward/outward dependency paths up to depth $N$, recording the complete explainability graph path (e.g. `workload/storyloom-api -> service/storyloom -> connects_to -> pgbouncer/infra-data`).
2. **RASCI Assignment:** Maps groups along the path to RASCI obligations based on service criticality and relationship semantics.
3. **Notification Routing:** Distinguishes between **Mandatory Operational Notices** (bypasses quiet hours, opt-out prohibited) and **Optional Subscriptions** (opt-in, respects quiet hours).
4. **Explainability Breadcrumbs:** Every notified party receives a precise explanation of why they were selected.

---

### 4. Human-Readable Decision Brief & Composite Approval Digest

Approval interfaces (Approval Relay, GitHub Deployment Gate, Temporal UI) enforce layered disclosure:
1. **Decision Summary:** Plain-language summary (What changes, why now, affected scope, expected customer impact, automatic safeguards).
2. **Explicit Acknowledgements:** Required check-boxes acknowledging connection retry expectations, rollback triggers, and plan hash binding.
3. **Composite Approval Context Digest:**
   $$H_{\text{approval context}} = \text{SHA-256}(\text{Plan Hash} \parallel \text{RASCI Policy Digest} \parallel \text{Impact Snapshot Digest} \parallel \text{Expected Behavior Digest} \parallel \text{Briefing Digest})$$

---

### 5. Multi-Channel Authorization & Progressive Enforcement

* **Three-Way Separation of Duties:**
  $$\text{OIDC Approver} \neq \text{GitHub Reviewer} \neq \text{Workflow Initiator}$$
* **Progressive Maturity Scale:**
  * Level 1 (Suggested): System computes and suggests RASCI with graph explainability.
  * Level 2 (Evidenced): Impact snapshot, RASCI, and expected behavior are mandatory plan digests.
  * Level 3 (Guarded): Missing Accountable/Responsible assignments block sensitive production changes.
  * Level 4 (Policy-Enforced): Required approvals and mandatory notices gate live execution.
  * Level 5 (Continuously Attested): CI graph, build provenance, runtime evidence, and governance policies are cryptographically linked and WORM-persisted.

## Consequences
* **Positive:** Complete visibility into change blast radius with deterministic graph-based stakeholder selection.
* **Positive:** Eradicates approval fatigue while guaranteeing Accountable authority and Consulted dependency notice.
* **Positive:** Human approvers sign an intelligible, plain-language decision brief cryptographically bound to the live technical plan.
* **Positive:** Durable, tamper-evident audit trail linking CMDB state, authorizations, and runtime execution metrics.

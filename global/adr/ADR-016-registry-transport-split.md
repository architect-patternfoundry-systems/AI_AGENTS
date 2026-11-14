# ADR-016: Deliberate Split Transport for Container Registry Access

## Status
Accepted

## Context
The registry migration incident revealed that the cluster uses a split-transport design:
- Image references use the canonical `registry-bridge.tailc2cafc.ts.net` identity
- K3s redirects node runtime pulls to the internal HTTP Registry service via mirror configuration
- External/operator access uses Tailscale HTTPS

This architecture was discovered incidentally during the migration, not designed deliberately. The key question is not "HTTP or HTTPS?" in isolation, but **which trust boundary should own node-to-registry traffic, and what security claims are we willing to make about it?**

## Decision
We adopt **Option A: Deliberate split transport** with explicit compensating controls and trigger-based path toward internal TLS.

### Architecture Definition
```yaml
node_runtime_pull_transport: >
  Continue using the K3s-configured internal HTTP mirror for node image pulls.
external_operator_transport: >
  Use registry-bridge.tailc2cafc.ts.net via Tailscale HTTPS.
artifact_identity: >
  Require canonical image repository references plus immutable sha256 digests
  for governed integration and future production workloads.
registry_publishing_authority: >
  Explicitly out of scope for this ADR; requires a separate registry capability decision.
internal_tls: deferred
canonical_https_node_pulls: not_claimed
```

### Split-Transport Model
```text
Git/Pod image reference:
  registry-bridge.tailc2cafc.ts.net/repository@sha256:<digest>

Node runtime resolution:
  K3s mirror → http://10.43.194.191:80

External/operator access:
  registry-bridge.tailc2cafc.ts.net:443
  → Tailscale ProxyGroup → Registry HTTP upstream
```

## Rationale
- **Operational resilience:** Node pulls do not depend on Tailscale DNS, tailnet reachability, ProxyGroup health, or public certificate flows
- **Low latency/locality:** Nodes pull from a cluster-local Registry service
- **Simple bootstrap:** K3s/containerd can pull during Tailnet or DNS disruption
- **Stable manifest identity:** Git can use a canonical hostname and immutable digest even when K3s transparently selects the local mirror
- **Consistency:** The identical `registries.yaml` hash across all nodes gives a strong baseline for a deliberately managed node-pull path
- **Avoids premature dependencies:** Does not turn a functioning local cluster dependency into a Tailscale/ProxyGroup dependency before registry publisher authority, immutability, and retention are solved

## Non-Goals
- Claiming encrypted node-to-registry transport
- Claiming registry publisher authentication
- Claiming immutable tags or deletion protection
- Migrating existing workload image references
- Changing registries.yaml or restarting K3s

## Compensating Controls
Option A is reasonable only with these controls:

### Image Identity
```yaml
integration_and_future_prod:
  required_format: "canonical-hostname/repository:tag@sha256:digest"
  reject:
    - ":latest"
    - "tilt-*"
    - "tag-only references"
```

### Mirror Configuration
```yaml
source_of_truth: "Git/OpenTofu/config-management"
drift_detection:
  - hash registries.yaml across every node
  - alert on unreviewed differences
service_identity:
  avoid: "hardcoded ClusterIP as long-term design dependency"
  future_state: "stable internal DNS endpoint or controlled service-discovery mechanism"
```

### Network Boundary
```yaml
registry_service:
  exposure: "cluster-internal only"
kubernetes_network_policy:
  allow_registry_access_only_from_required_namespaces: true
host_network:
  hardening: "restrict untrusted host access and node-level compromise"
```

### Transport Claims
```yaml
allowed_claim: "HTTPS protects external/operator registry access"
prohibited_claim: "All node image pulls use HTTPS"
```

### Artifact Recovery
```yaml
retain:
  - current_verified_digest
  - previous_verified_digest
verify:
  - pullability_from_every_node_runtime_class
  - digest_availability_before_rollout_approval
```

### Supply Chain (Deferred)
```yaml
deferred_separate_decision:
  - repository_scoped_ci_write_authority
  - immutable_tags
  - push_delete_audit_evidence
  - deletion_protection
  - artifact_provenance_enforcement
```

## Decision Triggers
Define objective conditions that reopen the ADR and force reconsideration of Option B or C:

| Trigger | Required response |
|---|---|
| Internal network becomes shared, untrusted, or reachable by guest/IoT devices | Move to internal TLS or isolated registry network |
| Sensitive or regulated artifact layers are introduced | Move to internal TLS and authenticated registry access |
| Registry ClusterIP changes or Service recreation breaks pulls | Replace hard-coded IP endpoint with durable service identity |
| Nodes already require Tailscale for core cluster operations | Reconsider canonical HTTPS node pulls |
| A registry platform upgrade is selected | Reassess internal TLS, repository authorization, immutability, audit, and retention together |
| Cross-cluster or remote-node pulls become common | Prefer canonical HTTPS or an authenticated internal TLS endpoint |
| A transport-integrity incident occurs | Escalate to Option C design immediately |

## Future Target
The strategic end state is not necessarily "all nodes use Tailscale HTTPS." It is:

```text
Node runtime → authenticated internal TLS registry endpoint
Operator/remote client → Tailscale HTTPS registry endpoint
CI → repository-scoped authenticated publish endpoint
GitOps → canonical digest reference
Admission → release approval bound to exact digest/workload/environment
Registry → immutable publication and retained rollback artifacts
```

This preserves local operational resilience while building real supply-chain authority. Tailscale Ingress can provide private HTTPS exposure for operator-facing services, but K3s registry mirror configuration remains a separate node-runtime path that must be explicitly governed.

## Consequences
### Positive
- **Operational resilience:** Node pulls independent of Tailscale infrastructure
- **Local performance:** Cluster-local registry access with low latency
- **Bootstrap simplicity:** K3s/containerd can pull during network disruption
- **Manifest stability:** Canonical identity preserved despite mirror resolution
- **Configuration consistency:** Identical registries.yaml hash across all nodes
- **Honest security claims:** HTTPS scope limited to external/operator access
- **Deferred complexity:** Internal TLS/PKI and registry authorization handled as separate investments

### Negative
- **No node-pull confidentiality:** Internal network traffic is unencrypted
- **No node-pull endpoint authentication:** HTTP does not prove registry identity
- **Service-IP coupling:** ClusterIP is an implementation address, not durable identity
- **Bypassed canonical HTTPS controls:** Node runtime does not exercise Tailscale TLS endpoint, ACLs, certificate validation
- **Split-path debugging complexity:** External HTTPS success does not prove node pulls, and vice versa
- **Publishing ungoverned:** Registry lacks authentication, writer scoping, retention, audit events, immutability

## Implementation
### Current State
- **Configuration Hash:** `6085e7758af30bf270fb9c4047d87c481eb1fd24bf5a6047341c791bb56f765b` (identical across cortex, synapse, ran-ubuntu-inspiron)
- **Mirror Configuration:** `registry-bridge.tailc2cafc.ts.net` → `http://10.43.194.191:80`
- **Transport:** HTTP for node pulls, HTTPS for external/operator access
- **Validation:** All three nodes validated for crictl pull success

### Required Actions
1. **Document current architecture** as intentional split-transport design
2. **Implement compensating controls** as defined in this ADR
3. **Establish digest-only policy** for governed integration and future production workloads
4. **Plan registry authority upgrade** (Harbor or equivalent) as next platform investment
5. **Monitor decision triggers** for escalation to Option B or C

## References
- [K3s Private Registry Configuration](https://docs.k3s.io/installation/private-registry)
- [Registry Migration Incident](/home/cortex/workspace/AI_AGENTS/global/incidents/active/2026-08-10-disk-space-cleanup-and-zombie-pod-analysis/)
- [ADR-015: Resource Resolution Priority Framework](/home/cortex/workspace/AI_AGENTS/global/adr/ADR-015-resource-resolution-priority.md)

## Related ADRs
- **ADR-015:** Resource Resolution Priority Framework (tiered resolution pattern)
- Future: Registry Authority and Supply Chain Governance (deferred)

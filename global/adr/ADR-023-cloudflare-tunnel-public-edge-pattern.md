# ADR-023: Cloudflare Tunnel Public-Edge Pattern for Browser-Only Services

**Status:** Staged — awaiting delta-security audit and dual sign-off per §1.1 of systems_architecture_policy-v9.1  
**Date:** 2026-07-13  
**Authors:** Lead Platform Architect  
**Supersedes:** N/A  
**Related:** systems_architecture_policy-v9.1 §1, §2.1; ADR-018 (Flux/Tilt Arbitration)

---

## Context

All cluster ingress currently uses `ingressClassName: tailscale` exclusively. This requires every end-user to have a Tailscale client installed and an authenticated Tailnet identity — appropriate for administrative and operator access, but a barrier for browser-only public dashboards intended for external stakeholders without Tailscale clients.

A `cloudflare-tunnel-token` Secret already exists in the `default` namespace (created 2026-05-10 via `kubectl-create`). No `cloudflared` Deployment is running. This ADR defines the pattern, eligibility criteria, origin hardening, and promotion gate to move Cloudflare Tunnel Ingress from **Staged** to **Enforced** in the policy table.

---

## Decision

Deploy `cloudflared` as a Flux-managed Deployment in a dedicated `cloudflared` namespace. Route only explicitly approved, browser-facing web dashboards through the tunnel. All other access paths remain on Tailscale. The tunnel token Secret is migrated from `default` to `cloudflared` namespace under SOPS management.

---

## Service Eligibility Criteria

A service may be routed through the Cloudflare Tunnel **only if all of the following are true**:

| Criterion | Requirement |
|---|---|
| Protocol | HTTP/HTTPS only. No TCP/SSH/database passthrough. |
| Payload type | No audio/video streaming, no bulk file transfer (>10 MB). Payloads offloaded to BYOB S3 pre-signed URLs. |
| Auth requirement | Cloudflare Access policy enforced. No anonymous public access without explicit approval. |
| Cluster isolation | Service bound to cluster-internal address only. No direct NodePort or LoadBalancer exposure. |
| Admin paths | Zero admin routes (SSH, metrics, DB, Kubernetes API) on the tunneled service. |
| Namespace | Must reside in `cloudflared-public` namespace or have an explicit NetworkPolicy allowing egress to `cloudflared` namespace only. |

**Services currently eligible:**
- CDMPC Governance Dashboard (Streamlit, port 8501) — when deployed

**Services explicitly excluded:**
- ToneRoot API, Storyloom API, talent-platform-api — admin/operator tools, Tailscale only
- Grafana, Prometheus, Alertmanager — observability, Tailscale only
- MinIO console/API — storage admin, Tailscale only
- Any service with database credentials in its environment

---

## Hostname Strategy

| Hostname | App | Dev Origin | Prod Origin | CF Access Policy |
|---|---|---|---|---|
| `canvas.patternfoundry.systems` | Neural Mesh Canvas | `localhost:8501` | `neural-mesh-canvas.cloudflared-public:8501` | Email OTP / `*.patternfoundry.systems` wildcard app |
| `pet.patternfoundry.systems` | Pet Canvas App | `localhost:8502` | `pet-canvas.cloudflared-public:8502` | Same |
| `rsvp.patternfoundry.systems` | Neural Mesh Canvas RSVP | `localhost:8503` | `neural-mesh-rsvp.cloudflared-public:8503` | Same |
| `cdmpc.patternfoundry.systems` | CDMPC Journey Widget | `localhost:8504` | `cdmpc-journey.cloudflared-public:8504` | Same |

Hostnames are managed in Cloudflare DNS via `cloudflared tunnel route dns`. Each tunnel ingress rule maps exactly one hostname to exactly one origin. Wildcard hostname tunnel rules are prohibited. A single CF Access Application with hostname `*.patternfoundry.systems` covers all four subdomains with one email OTP policy.

---

## Two Deployment Modes

This ADR governs two explicitly separate environments. They share the same tunnel UUID and CF Access policies but have different origin configurations. The k3s policy boundary (systems_architecture_policy-v9.1 §1) covers **Prod only**.

### Dev — Host Mode

```
External Browser
      │  HTTPS (TLS 1.3)
      ▼
Cloudflare Edge (WAF + Access)
      │  Encrypted outbound tunnel
      ▼
cloudflared (host process, not in k3s)
      │  localhost HTTP
      ▼
Streamlit apps (start_apps.sh, ports 8501-8504)
```

- Config: `neural_mesh_canvas/cloudflare_config.yml`
- Origins: `http://localhost:850x` (apps launched by `start_apps.sh`)
- Tunnel token: `~/.cloudflared/4a2d8a52-b6cf-4712-bc78-f093a890a12e.json`
- **Not a cluster ingress control.** Explicitly out of scope for k3s policy. No NetworkPolicies required.
- Run: `cloudflared tunnel --config neural_mesh_canvas/cloudflare_config.yml run`

| Subdomain | App | Port |
|---|---|---|
| `canvas.patternfoundry.systems` | Neural Mesh Canvas | 8501 |
| `pet.patternfoundry.systems` | Pet Canvas App | 8502 |
| `rsvp.patternfoundry.systems` | Neural Mesh Canvas RSVP | 8503 |
| `cdmpc.patternfoundry.systems` | CDMPC Journey Widget | 8504 |

### Prod — k3s Cluster Mode (Staged)

```
External Browser
      │  HTTPS (TLS 1.3)
      ▼
Cloudflare Edge (WAF + Access)
      │  Encrypted outbound tunnel
      ▼
cloudflared pod (namespace: cloudflared, Flux-managed)
      │  cluster-internal HTTP only
      ▼
ClusterIP Service → Pod (namespace: cloudflared-public)
```

- Config: `infrastructure_check/apps/cloudflared/configmap.yaml`
- Origins: `http://<service>.cloudflared-public.svc.cluster.local:850x`
- Tunnel token: `secret.sops.yaml` (SOPS/age encrypted, Flux-reconciled)
- Governed by NetworkPolicies in `network-policies.yaml`
- **Status: Staged** — apps not yet containerised; ClusterIP Services not yet deployed

## Architecture (Prod)

```
External Browser
      │  HTTPS (TLS 1.3)
      ▼
Cloudflare Edge (WAF + Access)
      │  Encrypted outbound tunnel
      ▼
cloudflared pod (namespace: cloudflared)
      │  cluster-internal HTTP only
      ▼
ClusterIP Service → Pod (namespace: cloudflared-public)
```

- `cloudflared` initiates an **outbound-only** connection to Cloudflare. No inbound ports required on the cluster or host firewall.
- Origin pods listen on cluster-internal ClusterIP only. No NodePort, no LoadBalancer.
- `cloudflared` namespace has egress allowed only to `443/tcp` external and ingress only from `cloudflared-public` namespace.
- `cloudflared-public` namespace has egress only to `cloudflared` namespace and BYOB S3 endpoints.

## Origin Hardening Rules

1. **No direct inbound ports**: Host firewall (Tailscale ACL + cloud security group) drops all inbound traffic not sourced from `100.64.0.0/10`. Tunneled services are unreachable by IP.
2. **Service binding**: All tunneled services bind to `ClusterIP` only. `kubectl get svc` must show no `NodePort` or `LoadBalancer` type for any tunneled service.
3. **NetworkPolicy — `cloudflared` namespace**:
   - Egress: `443/tcp` to `0.0.0.0/0` (Cloudflare edge) + DNS `53/udp`
   - Ingress: from `cloudflared-public` namespace pods only (for tunnel routing)
   - No ingress from Tailscale CIDRs required (cloudflared is not user-facing)
4. **NetworkPolicy — `cloudflared-public` namespace**:
   - Egress: to `cloudflared` namespace (HTTP to tunnel daemon) + S3 endpoints `443/tcp` (for pre-signed URL offload) + DNS
   - Ingress: from `cloudflared` namespace only
   - No direct Tailscale ingress
5. **Cloudflare Access**: Every tunneled hostname has an Access Application with at minimum an email OTP policy. Service tokens used for any machine-to-machine paths.
6. **Payload offload**: Any response body > 10 MB must use a pre-signed S3 URL redirect. Audio/video is never served through the tunnel.

---

## Failure Modes and Mitigations

| Failure | Impact | Mitigation |
|---|---|---|
| `cloudflared` pod crash | Tunneled services unreachable externally | Pod `restartPolicy: Always`, liveness probe on metrics port `2000`. Tailscale path unaffected. |
| Cloudflare edge outage | Tunneled services unreachable externally | Services remain reachable on Tailscale for operators. SLA accepted (Cloudflare 99.99% uptime). |
| Tunnel token compromise | Attacker can route traffic to tunneled services | Rotate token immediately via Cloudflare dashboard; SOPS-encrypted Secret re-applied by Flux. CF Access policies remain enforced independently of the tunnel token. |
| Misconfigured tunnel rule exposes admin service | Admin service reachable externally | Prevented by NetworkPolicy: admin namespaces have no egress path to `cloudflared` namespace. Tunnel config is declarative and GitOps-reconciled. |
| CF Access policy misconfigured | Unauthenticated access to dashboard | Cloudflare Access is enforced at the edge before traffic reaches the tunnel. Second line: service has no sensitive data without authenticated session. |
| Large payload sent through tunnel | CF plan-tier violation / account block | Enforced by response middleware: redirect payloads > 10 MB to S3 pre-signed URL. |

---

## Promotion Gate (Staged → Enforced)

The §1 table entry moves from **Staged** to **Enforced** when all of the following are evidenced:

1. `cloudflared` Deployment is Flux-reconciled in `cloudflared` namespace and healthy.
2. Tunnel token Secret is SOPS-encrypted and managed by Flux (not `kubectl-create`).
3. At least one eligible service is routed through the tunnel with a CF Access policy active.
4. `kubectl get svc -A | grep -E 'NodePort|LoadBalancer'` returns no tunneled services.
5. `kubectl get networkpolicy -n cloudflared` shows egress-only policy to CF edge.
6. Delta-security audit completed and signed off by Lead Platform Architect + SSO per §1.1.

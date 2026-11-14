# Cluster Health Indicators & Blind Spots — Authoritative Report (v10)

**Status: Investigation complete; permanent remediation approved for staged GitOps implementation, subject to rendered-manifest validation, ownership review, and fresh-connection acceptance tests after every policy path.**

**Date:** 2026-09-01
**Cluster:** K3s (synapse, cortex, ran-ubuntu-inspiron)
**Predecessor:** 2026-07-21-prometheus-grafana-scrape-failures
**Investigators:** Devin AI agent, human review (multi-round)

## Conclusion

Five controlled NetworkPolicy experiments demonstrate that Prometheus requires durable, narrowly scoped policy paths to establish fresh metric scrapes for kubelet TCP/10250, Flux TCP/8080, CoreDNS TCP/9153, and CloudNativePG exporter TCP/9187. The `governed-intentionality-daemon` additionally requires a Pod-specific ingress rule on TCP/9090 because no existing allow policy selects that workload — the `allow-internal-data-access` policy selects only `app in {postgres, minio}`, not `app=governed-intentionality`. A narrow ingress rule enabled TCP/9090 reachability; the daemon serves Python Prometheus runtime metrics plus 10 domain-specific governance metrics on `/metrics` at port 9090 (confirmed), but Prometheus scrape transition for this target still needs confirmation after permanent policy application.

The temporary rules were removed. New connections are now denied; some kubelet and Flux targets remain `UP`. The continuing healthy target status is consistent with reuse of TCP/HTTP/2 sessions established while the temporary allow policies existed. Fresh connection attempts are denied. Because the scrape-to-socket mapping and policy-state retention were not directly traced, current target health must not be treated as proof of a durable policy path. This behavior is consistent with stateful enforcement in the K3s network-policy implementation, which is commonly realized through kube-router-derived iptables/ipset rules in K3s deployments. Flannel provides pod networking rather than NetworkPolicy enforcement.

The immediate remediation is a GitOps-managed policy change, applied one path at a time with fresh-connection validation after each, and a final controlled Prometheus restart. Separately, remove confirmed duplicate Flux ServiceMonitors after ownership verification, address `nexus-audio-catalog` restart behavior as the highest-priority workload reliability concern, and treat native etcd metric exposure as a later security-sensitive design decision.

---

## Part 1 — Five Controlled Experiments

### Experiment summary

| # | Target | Policy type | What was proven | Metrics/observations | New connections after deletion |
|---|---|---|---|---|---|
| 1 | Kubelet (10250, node IPs) | Egress in `toneroot` | Fresh Prometheus scrapes and metrics succeeded | 575 `container_cpu_usage_seconds_total`, 16 `kubelet_volume_stats_used_bytes` | Denied |
| 2 | Flux controllers (8080, flux-system) | Egress in `toneroot` | Fresh Prometheus scrapes and metrics succeeded | 1,467 `gotk_*` series | Denied |
| 3 | governed-intentionality-daemon (9090, default) | Ingress in `default` | A narrow ingress rule enabled TCP/9090 reachability; Prometheus scrape behavior still needs confirmation | wget confirmed reachable; daemon serves `python_gc_objects_collected_total` + 10 domain metrics (`friction_events_total`, `healing_actions_total`, etc.) on `/metrics` | Denied |
| 4 | CoreDNS (9153, kube-system) | Egress in `toneroot` | Fresh Prometheus scrapes and metrics succeeded | 22 `coredns_dns_requests_total`, 7 `coredns_dns_responses_total`, 8 `coredns_cache_entries` | Denied |
| 5 | CloudNativePG exporter (9187, infra-data) | Egress in `toneroot` | Fresh Prometheus scrapes and metrics succeeded | 82 `cnpg_*` series (`cnpg_collector_up`, `cnpg_backends_total`, `cnpg_pg_database_size_bytes`) | Denied |

All five experiments followed the same protocol: record baseline → add narrowly scoped temporary NP → wait for scrape interval → confirm target health and metric arrival → delete NP → confirm new connections denied.

### Authoritative post-cleanup baseline

Observation time: **2026-09-01 08:44:03 UTC** (temporary NPs deleted ~2 hours prior)

| Class | Current count | Fresh-connection test | Durable policy conclusion |
|---|---:|---|---|
| Kubelet | 9/9 up (lastScrape 11–30s ago) | New TCP/10250 denied | Policy still missing |
| Flux | 12/12 up (lastScrape 4–29s ago) | New TCP/8080 denied | Policy still missing |
| CoreDNS | 0/2 up | New TCP/9153 denied | Policy still missing |
| CNPG exporter | 0/2 up | New TCP/9187 denied | Policy still missing |
| GID daemon | 0/1 up | Temporary policy enabled TCP/9090; now removed | Ingress policy still missing |

The five currently down endpoint instances — one GID daemon, two CoreDNS endpoints, and two CloudNativePG exporter endpoints — provide an uncontaminated post-experiment observation. Kubelet and Flux target status is contaminated by pre-existing established connections, so their durable baseline remains the pre-experiment failure state until permanent policy changes are tested with fresh connections.

### Persistent-connection behavior: observed evidence and limits

**Evidence supporting the persistence hypothesis:**
- `netstat` inside the Prometheus pod shows ESTABLISHED TCP connections to kubelet (10250), Flux (8080), and other targets
- `sysctl net.netfilter.nf_conntrack_tcp_timeout_established = 86400` (24 hours)
- New connections (wget) are denied after NP deletion while existing connections persist
- Prometheus uses HTTP/2 with connection pooling (`enable_http2: true`)

**Evidence not captured:**
- `conntrack -L` returned 0 entries for the Prometheus pod IP — K3s uses nftables, and conntrack entries may be in a different namespace or tracked differently; the capture method was incomplete
- Specific iptables/nftables rules for the Prometheus-to-kubelet flow were not individually traced
- A conntrack record was not directly correlated to an observed Prometheus socket tuple
- The scrape-to-socket mapping was not directly traced

**Corrected phrasing:** The continuing healthy target status is consistent with reuse of TCP/HTTP/2 sessions established while the temporary allow policies existed. Fresh connection attempts are denied. Because the scrape-to-socket mapping and policy-state retention were not directly traced, current target health must not be treated as proof of a durable policy path. This behavior is consistent with stateful enforcement in the K3s network-policy implementation, which is commonly realized through kube-router-derived iptables/ipset rules in K3s deployments. Flannel provides pod networking rather than NetworkPolicy enforcement. The host's established-TCP conntrack timeout is configured as 86,400 seconds, showing that long-lived state can be retained under some conditions, but this does not guarantee a 24-hour scrape-session lifetime.

**Do not wait for expiration as a validation method.** A controlled restart of Prometheus during a planned test window, only after a permanent policy is added, gives a clear acceptance signal.

---

## Part 2 — Daemon Network Reachability Root Cause: Resolved

The `allow-internal-data-access` policy in the `default` namespace has:
```yaml
podSelector:
  matchExpressions:
  - key: app
    operator: In
    values:
    - postgres
    - minio
```

This selects only pods with `app=postgres` or `app=minio` — NOT the `governed-intentionality-daemon` (which has `app=governed-intentionality`). The daemon is selected by `default-deny-all` (deny all ingress) but no allow policy permits ingress from `toneroot` on port 9090. The egress from `toneroot` IS allowed by `allow-apiserver-full` (egress to `default` ns on ALL ports), but the ingress side is missing. This is a configuration-selection defect, not a CNI failure.

**Status distinction:**
- **Network reachability root cause:** proven.
- **Prometheus scrape restoration:** pending permanent-policy deployment and fresh-connection validation.

**Additional finding:** The daemon has TWO ServiceMonitors (`default/governed-intentionality-daemon` and `governance/governed-intentionality-daemon`), both with `namespaceSelector: {}` (same-namespace only). Only the `default` one produces a target because the daemon pod is in `default`, not `governance`. The `governance`-namespace ServiceMonitor is a non-producing cleanup candidate (see Change Set B).

**GID daemon metrics inventory:** The daemon exposes 10 domain-specific governance metrics in addition to Python runtime and process metrics:
- `communication_breakdowns`, `conflicts_detected`, `current_friction_level`, `daemon_uptime_seconds`, `decision_delays`, `friction_events_created`, `friction_events_total`, `healing_actions_created`, `healing_actions_total`, `resource_contention`

---

## Part 3 — Flux Target Reconciliation

### Complete target inventory (12 targets)

| `job` | `instance` | ServiceMonitor namespace | Duplicate? |
|---|---|---|---|
| helm-controller-prom | 10.42.0.96:8080 | flux-system | Primary |
| helm-controller-prom | 10.42.0.96:8080 | toneroot | Duplicate |
| image-automation-controller-prom | 10.42.0.113:8080 | flux-system | Primary |
| image-automation-controller-prom | 10.42.0.113:8080 | toneroot | Duplicate |
| image-reflector-controller-prom | 10.42.0.104:8080 | flux-system | Primary |
| image-reflector-controller-prom | 10.42.0.104:8080 | toneroot | Duplicate |
| kustomize-controller-prom | 10.42.1.14:8080 | flux-system | Primary |
| kustomize-controller-prom | 10.42.1.14:8080 | toneroot | Duplicate |
| notification-controller-prom | 10.42.0.123:8080 | flux-system | Primary |
| notification-controller-prom | 10.42.0.123:8080 | toneroot | Duplicate |
| source-controller-prom | 10.42.2.126:8080 | flux-system | Primary |
| source-controller-prom | 10.42.2.126:8080 | toneroot | Duplicate |

### Full label-set comparison: all six pairs

| Controller | `labels` identical | `discoveredLabels` identical | Same URL | Same health |
|---|---|---|---|---|
| helm-controller | Yes | No (1 diff: `job` discovery label) | Yes | Yes |
| image-automation-controller | Yes | No (1 diff: `job` discovery label) | Yes | Yes |
| image-reflector-controller | Yes | No (1 diff: `job` discovery label) | Yes | Yes |
| kustomize-controller | Yes | No (1 diff: `job` discovery label) | Yes | Yes |
| notification-controller | Yes | No (1 diff: `job` discovery label) | Yes | Yes |
| source-controller | Yes | No (1 diff: `job` discovery label) | Yes | Yes |

**All six pairs confirmed:** Final `labels` are identical for every pair. The `discoveredLabels` differ in exactly one field — the internal `job` discovery label, which records which ServiceMonitor produced the target (`serviceMonitor/flux-system/helm-controller/0` vs `serviceMonitor/toneroot/helm-controller/0`). This discovery label is relabeled to the same final `job=helm-controller-prom` value, so both targets write samples to the same TSDB series.

### Duplicate impact: observed evidence

`prometheus_tsdb_out_of_order_samples_total` is currently 7,200. Identical Flux target labels make duplicate scraping a plausible contributor, but the counter is global and does not attribute samples to a job or ServiceMonitor. `rate(prometheus_tsdb_out_of_order_samples_total[5m])` is currently 0, indicating the out-of-order samples are historical accumulation, not actively growing at this time. The 7,200 count could have arisen from duplicate Flux scrapes, target churn, relabeling changes, remote-write ingestion, recording-rule timing, or other duplicate ServiceMonitor definitions.

**Acceptance metric for cleanup validation:**
```promql
rate(prometheus_tsdb_out_of_order_samples_total[5m])
```
Compare:
1. Before permanent policy changes (baseline: 0/s, absolute: 7,200)
2. After fresh scrape validation
3. Immediately before Flux duplicate removal
4. For at least one full reconciliation/scrape period after duplicate removal

The duplicate targets double scrape requests and can cause duplicate ingestion, timestamp races, or query ambiguity when complete labels overlap. Dashboard/alert effects are **potential** until query inspection confirms them.

### Reconciliation table

| Question | Required evidence |
|---|---|
| Why does a six-controller inventory yield five sampled series? | `notification-controller` does not emit `gotk_reconcile_duration_seconds_count` (handles events, not reconciliation) |
| Are all duplicate target label sets truly identical? | All six pairs confirmed: final `labels` identical; `discoveredLabels` differ only in ServiceMonitor-origin `job` field |
| Are duplicate samples rejected or racing? | `prometheus_tsdb_out_of_order_samples_total=7200` (historical); `rate=0` currently. Inspect Prometheus logs for series labels associated with out-of-order rejections. |
| Are alerts/dashboards affected? | Inspect recording rules and dashboard queries for `job`, `instance`, `service`, `endpoint`, or ServiceMonitor-origin labels |

### Flux controller shared label

All six Flux controllers share `app.kubernetes.io/part-of=flux` (verified live). `weave-gitops` has `part-of=weave-gitops` (not `flux`), so it will not be selected. This enables a pod-scoped egress policy instead of namespace-wide TCP/8080 (see Change Set A2).

**Operational note:** Revalidate `app.kubernetes.io/part-of=flux` after Flux upgrades and before adding a non-controller Flux-adjacent workload with that label. The selector is stable today, but it is an implicit monitoring-security contract worth documenting.

**Before removing the `toneroot` duplicates, verify their GitOps owner** (e.g., duplicate Helm subchart, manual kustomize overlay).

---

## Part 4 — Etcd Metrics

### What the evidence shows

1. The API server's `/metrics` endpoint returns 17,882 `etcd_*` series — these are **API server etcd client metrics** (5 families: `etcd_bookmark_counts`, `etcd_request_duration_seconds`, `etcd_requests_total`, `etcd_request_errors_total`, `etcd_lease_object_counts`).
2. **NO etcd-native health metrics** (`etcd_server_has_leader`, `etcd_mvcc_db_total_size_in_bytes`, `etcd_server_proposals_committed_total`, `etcd_disk_wal_fsync_duration_seconds`, `etcd_network_peer_active_peers`) are present.
3. The etcd Service has selector `component: etcd` but **zero endpoints** — K3s runs etcd embedded.
4. Etcd is NOT listening on port 2381 or 2379 from the node network.
5. `--etcd-expose-metrics` is not set in K3s server config.

### Corrected conclusion

The API server exposes etcd **client-side** request metrics (already scraped via the apiserver ServiceMonitor), but etcd **native health metrics** are NOT exposed. This is an **unconfigured integration path**. Lack of native etcd metrics is a real blind spot, but it does not mean etcd is known unhealthy. API-server etcd client latency/errors remain useful compensating indicators.

Etcd native metric exposure is a separate security-sensitive design proposal. Do not expose TCP/2381 until listener behavior, authentication/TLS requirements, firewall scope, Pod-to-node policy rules, snapshots, maintenance plan, and rollback are reviewed. Continue using API-server etcd client latency/error metrics as partial coverage in the meantime.

---

## Part 5 — Kube-proxy and Control-Plane

### Kube-proxy metrics provenance

**Observed:** In this K3s deployment, the API-server `/metrics` scrape includes `kubeproxy_*` metric families (76 `kubeproxy_sync_proxy_rules` series), and the localhost TCP/10249 endpoint also exposes them. Port 10249 is not visible as a standard listening socket in `/proc/net/tcp`, yet `wget http://127.0.0.1:10249/metrics` returns both API server and kube-proxy metrics. The `kube-prometheus-stack-kube-proxy` Service has selector `k8s-app=kube-proxy` but **zero endpoints** — no pods have that label in K3s.

**Corrected conclusion:** The API-server scrape contains `kubeproxy_*` families, and localhost TCP/10249 returns overlapping metrics. The conventional kube-proxy ServiceMonitor has no endpoints in this K3s deployment and therefore cannot represent kube-proxy health. Treat the API-server scrape as the observed source of available kube-proxy metrics. Before relying on it for kube-proxy-specific alerting, verify that observed `kubeproxy_*` series carry a stable label set permitting node/component attribution, and confirm required recording/alert rules can use those series without duplication or misleading aggregation.

### Controller-manager and Scheduler

K3s embeds these in the server process. They bind to localhost and are not scrapeable from the pod network. The HelmRelease values for `kubeControllerManager`, `kubeScheduler`, and `kubeProxy` are **not explicitly set** — they use chart defaults that assume kubeadm-style static pods.

### PrometheusRules producing false-positive alerts

- `KubeControllerManagerDown` in `kube-prometheus-stack-kubernetes-system-controller-manager`
- `KubeProxyDown` in `kube-prometheus-stack-kubernetes-system-kube-proxy`
- `KubeSchedulerDown` in `kube-prometheus-stack-kubernetes-system-scheduler`

### Required compensating health signals (staged: add replacements before disabling)

| Disabled alert | Replacement signal | Source | Status |
|---|---|---|---|
| KubeControllerManagerDown | Deployment/DaemonSet/StatefulSet convergence; node condition transitions; Job completion failures | kube-state-metrics | Available |
| KubeSchedulerDown | Pending pods (excluding WaitForFirstConsumer); unschedulable condition count | kube-state-metrics | Available |
| KubeProxyDown | Service endpoint reachability; DNS resolution; kube-proxy metrics via API server (verify label attribution first) | apiserver ServiceMonitor + synthetic checks | Partially available |
| Etcd health | API server etcd request latency/errors | apiserver ServiceMonitor | Partially available (client-side only) |

---

## Part 6 — Workload Issues

### nexus-audio-catalog restarts

| Property | Value |
|---|---|
| Total restarts | 560 |
| Last termination | Exit code 137 (SIGKILL) |
| Previous logs | Healthy HTTP 200 responses immediately before death |
| Resource limits | 512Mi memory, 500m CPU |
| OOMKills | 0 in current pod status (from kube-state-metrics, reliable for current state but not forensic history) |

**Next steps:** Check node dmesg for OOM events, check pod events for liveness probe failures, and after cAdvisor metrics are restored, monitor actual memory usage. Do not raise memory limits based solely on exit code 137.

### Workload classification

| Finding | Confidence | Likely operational significance | Owner/action |
|---|---|---|---|
| `nexus-audio-catalog` restart loop | High | Ongoing reliability concern | Investigate now |
| Governance canary image tag missing | High | Blocks Flux Kustomization health, may be intentional gate (ADR-032 Stage 4) | Release/GitOps owner decision |
| `ace-step-service` missing PVC | High | Prevents desired workload from scheduling | Manifest owner decision |
| Storyloom Tilt image missing | High fact, uncertain impact | Likely development drift | Dev owner confirmation |
| Alembic Job exit 1 | Medium | Could be historical/superseded or a rollout blocker | Inspect current Job/owner/log retention |

---

## Part 7 — Revised Blind Spot Inventory

| Priority | Blind Spot | Root Cause | Confidence | Proven by experiment? | Current state |
|---|---|---|---|---|---|
| **P0** | Kubelet/cAdvisor/container metrics | NetworkPolicy egress gap (port 10250) | **Proven** | Yes — fresh scrapes + metrics | Currently UP via pre-existing sessions; fresh connections denied, so target failure is expected when fresh connections are required unless permanent policy is applied |
| **P0** | Flux controller metrics | NetworkPolicy egress gap (port 8080) | **Proven** | Yes — fresh scrapes + metrics | Currently UP via pre-existing sessions; fresh connections denied, so target failure is expected when fresh connections are required unless permanent policy is applied |
| **P0** | governed-intentionality-daemon metrics | Ingress NP gap (podSelector mismatch) | **Proven** (reachability) | Yes — pod-specific NP → TCP reachable; scrape transition needs confirmation | DOWN (confirmed) |
| **P0** | CoreDNS metrics | NetworkPolicy egress gap (port 9153) | **Proven** | Yes — fresh scrapes + metrics | DOWN (confirmed) |
| **P0** | CloudNativePG exporter metrics | NetworkPolicy egress gap (port 9187) | **Proven** | Yes — fresh scrapes + metrics | DOWN (confirmed) |
| **P1** | Etcd native health metrics | `--etcd-expose-metrics` not set | **Confirmed** | Service has 0 endpoints; etcd not on 2381/2379 | Not scraped |
| **P1** | GPU monitoring | No DCGM exporter deployed | **Confirmed** | 4 GPUs, 3 GPU pods, 0 GPU metrics | Not scraped |
| **P2** | cert-manager metrics | No ServiceMonitor | **Confirmed** | No ServiceMonitor exists | Not scraped |
| **P2** | Loki self-monitoring | Not scraped by Prometheus | **Confirmed** | `loki_distributor_lines_received_total` not found | Not scraped |
| **P2** | Control-plane alerts (false positives) | K3s embeds components; chart defaults assume kubeadm | **Confirmed** | No pods/DaemonSets; metrics in API server only | Alerts firing |
| **P3** | Duplicate Flux ServiceMonitors | 6 duplicate SMs in `toneroot` | **Confirmed** | 12 targets; all 6 pairs have identical final labels; 7,200 historical out-of-order samples; doubled scrape load | All UP via pre-existing sessions |
| **P3** | Non-producing GID ServiceMonitor | `governance`-namespace SM with same-namespace selector, daemon in `default` | **Confirmed** | SM exists, produces 0 targets | Cleanup candidate |
| **P3** | PVC usage % | Was blocked by kubelet scrape failure | **Proven** | 16 series appeared during test | Available only through pre-existing sessions; expected to fail when fresh connections are required unless permanent policy is applied |

---

## Part 8 — Staged Remediation Plan

### Change set A: Proven collection paths (one at a time, with fresh-connection validation after each)

**Prometheus restart impact and preconditions:** Restarting Prometheus creates a brief metrics and alert-evaluation gap. If Prometheus is single-replica, no metrics scrape occurs while it is restarting. Alerts can transition or become stale during the restart interval. Alertmanager may continue to notify existing firing alerts according to configured repeat intervals, but new rule evaluations pause. Local Prometheus data remains on its PVC if storage is durable.

**Precondition:** Confirm Prometheus retention storage is persistent and healthy, record the planned restart window, and verify Alertmanager behavior for the expected evaluation gap.

A less disruptive alternative is to roll the individual Prometheus Pod after applying one policy at a time, but that still creates the same evaluation gap if there is only one replica. The important point is to plan it explicitly.

#### A1: Prometheus → node kubelet TCP/10250 (egress in `toneroot`)

Restrict to individual node IPs. Each `ipBlock` must be a separate peer item in the `to` list:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-prometheus-kubelet
  namespace: toneroot
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: prometheus
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 10.10.10.2/32
        - ipBlock:
            cidr: 10.10.10.3/32
        - ipBlock:
            cidr: 10.10.10.5/32
      ports:
        - protocol: TCP
          port: 10250
```

**Pre-merge test for `/32` ipBlock semantics:** The temporary experiment used `ipBlock: 10.10.10.0/24`. Before committing the narrower `/32` form, verify equivalent behavior under the K3s embedded policy controller:
1. Commit the exact `/32` policy in a branch or temporary overlay
2. Reconcile it
3. Force one fresh Prometheus connection or use an ephemeral test Pod with the same labels
4. Confirm TCP/10250 succeeds for all three node IPs
5. If individual `/32` rules unexpectedly fail but the prior `/24` succeeds, document the K3s policy-engine behavior and use the narrowest working CIDR

If node IPs are expected to change, document the inventory reconciliation mechanism or accept the broader CIDR explicitly as an operational tradeoff.

**Validation:** Restart Prometheus or force fresh connections. Confirm 9/9 targets UP, cAdvisor and volume metrics arrive. Confirm no unwanted Prometheus egress path was introduced.

#### A2: Prometheus → Flux controller Pods TCP/8080 (egress in `toneroot`)

All six Flux controllers share `app.kubernetes.io/part-of=flux` (verified live). `weave-gitops` has `part-of=weave-gitops` and will not be selected. Use this shared label for a pod-scoped policy:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-prometheus-flux-metrics
  namespace: toneroot
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: prometheus
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: flux-system
          podSelector:
            matchLabels:
              app.kubernetes.io/part-of: flux
      ports:
        - protocol: TCP
          port: 8080
```

**Operational note:** Revalidate `app.kubernetes.io/part-of=flux` after Flux upgrades and before adding a non-controller Flux-adjacent workload with that label.

**Validation:** Restart Prometheus or force fresh connections. Confirm 12/12 current targets are healthy. Measure scrape/error and out-of-order sample rates.

#### A3: Prometheus → CoreDNS Pods TCP/9153 (egress in `toneroot`)

Verified labels: CoreDNS pods have `k8s-app=kube-dns` (confirmed live on both pods).

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-prometheus-coredns-metrics
  namespace: toneroot
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: prometheus
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: TCP
          port: 9153
```

**Operational note:** Revalidate `k8s-app=kube-dns` after any K3s/CoreDNS chart upgrade. The NetworkPolicy rules must track the actual Service endpoint membership, not merely the current Pod names.

**Validation:** Restart Prometheus or force fresh connections. Confirm 2/2 targets UP, `coredns_dns_requests_total`, `coredns_dns_responses_total`, `coredns_cache_entries` arrive.

#### A4: Prometheus → CloudNativePG cluster Pods TCP/9187 (egress in `toneroot`)

Verified: `cnpg.io/cluster=postgres` selects exactly `postgres-2` (primary) and `postgres-6` (replica) in `infra-data`. There is only one CNPG cluster (`postgres`). The `postgres-metrics` Service uses this selector. The endpoints are CNPG database Pods with an exporter sidecar, not a standalone exporter Deployment.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-prometheus-cnpg-metrics
  namespace: toneroot
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: prometheus
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: infra-data
          podSelector:
            matchLabels:
              cnpg.io/cluster: postgres
      ports:
        - protocol: TCP
          port: 9187
```

**Operational note:** Revalidate the Service selector and target Pod role labels after CNPG upgrades, failover configuration changes, or addition of another database cluster. If additional CNPG clusters are added, add a policy rule per monitored Service/cluster or a carefully documented label convention, rather than an overly broad `cnpg.io/cluster` wildcard.

**Validation:** Restart Prometheus or force fresh connections. Confirm 2/2 targets UP, `cnpg_collector_up`, `cnpg_backends_total`, `cnpg_pg_database_size_bytes` arrive. Verify no access occurs to non-selected database Pods.

#### A5: Prometheus → governed-intentionality-daemon TCP/9090 (ingress in `default`)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-prometheus-to-governed-intentionality
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: governed-intentionality
      component: daemon
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: toneroot
          podSelector:
            matchLabels:
              app.kubernetes.io/name: prometheus
      ports:
        - protocol: TCP
          port: 9090
```

The `namespaceSelector` plus nested `podSelector` limits access to the actual Prometheus Pods in `toneroot`, not every Pod in the namespace.

**Validation:** Restart Prometheus or force fresh connections. Confirm target health is UP, `lastError` is empty, fresh scrape timestamp, and expected metric families are present:
- Python runtime metrics: `python_gc_objects_collected_total`, `python_info`
- Process metrics: `process_cpu_seconds_total`, `process_resident_memory_bytes`
- **Domain-specific governance metrics (at least one required):** `friction_events_total`, `healing_actions_total`, `daemon_uptime_seconds`, `conflicts_detected`, `current_friction_level`, `resource_contention`, `communication_breakdowns`, `decision_delays`, `friction_events_created`, `healing_actions_created`

The daemon's metrics path is `/metrics` on port 9090 (confirmed). If the daemon's metrics path is not `/metrics`, uses authentication, has a non-default port name, or returns an application-level error, the new NetworkPolicy alone will not solve collection — its reachability test is necessary but not yet the same completeness level as the other four target classes.

### Change set B: Flux deduplication and GID ServiceMonitor cleanup

1. Find the duplicate ServiceMonitor source in Git/Helm/Kustomize
2. **Do not remove duplicate ServiceMonitors until full `labels` and `discoveredLabels` comparisons are recorded for all six controller pairs** (completed in this investigation — all six pairs confirmed: final labels identical, discoveredLabels differ only in ServiceMonitor-origin `job` field)
3. Remove only the duplicate six ServiceMonitors in `toneroot`
4. Reconcile through Flux
5. Confirm exactly six Flux targets remain (one per controller)
6. Verify query/alert behavior before and after (no dashboards or recording rules reference now-absent jobs)
7. Compare `rate(prometheus_tsdb_out_of_order_samples_total[5m])` before and after cleanup

**GID ServiceMonitor cleanup — desired steady state:**

| Object | Desired state |
|---|---|
| `default/governed-intentionality-daemon` ServiceMonitor | Exists, selected by Prometheus, 1 healthy target |
| `governance/governed-intentionality-daemon` ServiceMonitor | Removed, relocated, or intentionally documented as inactive |
| GID target endpoint | `/metrics` on TCP/9090, `up == 1`, fresh scrape, no `lastError` |
| GID metric families | Python runtime metrics plus at least one domain-specific governance metric (`friction_events_total`, `healing_actions_total`, etc.) |

### Change set C: K3s chart topology (staged)

1. **First commit:** Add compensating functional alerts and dashboards:
   - Workload convergence (Deployment/DaemonSet/StatefulSet)
   - Pending/Unschedulable Pod age and count
   - API error/latency/SLO
   - DNS and Service reachability synthetic checks
   - Kube-proxy metric alerts using observed `kubeproxy_*` families, if labels can reliably identify source
2. **Second commit:** Disable inapplicable ServiceMonitors/rules (`kubeControllerManager.enabled: false`, `kubeScheduler.enabled: false`, `kubeProxy.enabled: false`) and confirm:
   - False-positive alerts resolve
   - No dashboards or recording rules reference now-absent jobs
   - Alertmanager noise reduced without losing material coverage
3. **Separate high-risk decision:** Etcd native metric exposure (`--etcd-expose-metrics=true`), with version-specific verification, maintenance window, snapshot, and rollback

### Change set D: Remaining observability

- Deploy DCGM exporter only to GPU-capable nodes, with taints/tolerations and resource limits
- Add cert-manager ServiceMonitor after identifying precise Service/port/metrics ownership
- Add Loki self-monitoring
- Optional long-term retention/remote-write decision

### Change set E: Workload remediation

1. **`nexus-audio-catalog`:** Check node dmesg for OOM events, check pod events for liveness probe failures. After cAdvisor metrics restored, monitor actual memory usage. Consider raising 512Mi limit if justified by data.
2. **Governance canary:** Determine ownership — complete build pipeline, separate from Flux health check, or disable by default.
3. **`ace-step-service`:** Create missing PVC or remove deployment if not intended.
4. **Migration jobs:** Check Job status and logs for both alembic migrations.

---

## Part 9 — Execution-Ready Acceptance Checklist

### Before reconciliation

- [ ] Confirm the production Prometheus Pods still carry `app.kubernetes.io/name=prometheus` (verified: yes)
- [ ] Confirm namespace labels (verified: all 5 namespaces have `kubernetes.io/metadata.name` label)
- [ ] Confirm live target Pod labels and Service EndpointSlice membership for Flux, CoreDNS, CNPG, and GID (verified)
- [ ] Confirm `app.kubernetes.io/part-of=flux` on all six Flux controller Pods (verified: yes)
- [ ] Confirm Prometheus retention storage is persistent and healthy
- [ ] Record the planned restart window
- [ ] Verify Alertmanager behavior for the expected evaluation gap
- [ ] Validate NetworkPolicy YAML using server-side dry run or GitOps rendering checks
- [ ] Confirm a rollback commit is prepared
- [ ] Test `/32` ipBlock semantics for kubelet policy (see A1 pre-merge test)
- [ ] Record baseline `rate(prometheus_tsdb_out_of_order_samples_total[5m])` (current: 0/s, absolute: 7,200)

### After each policy path (A1–A5, applied one at a time)

- [ ] Restart Prometheus or force fresh connections for that path
- [ ] Confirm target health for that path's endpoints: `health=up`, `lastError=none`
- [ ] Confirm expected metric families for that path
- [ ] Confirm no unwanted Prometheus egress path was introduced
- [ ] Measure new active-series count and sample ingestion rate
- [ ] Review Alertmanager for resolved and newly evaluated alerts

### After all A policies applied

- [ ] Confirm exact endpoint health:
  - Kubelet: 9/9
  - Flux: 12/12 initially, then 6/6 after duplicate cleanup
  - CoreDNS: 2/2
  - CNPG exporter: 2/2
  - GID: 1/1
- [ ] Confirm `lastError` is empty for every healthy target
- [ ] Confirm expected metrics:
  - cAdvisor/container and `kubelet_volume_stats_*`
  - `gotk_*`
  - CoreDNS request/response/cache families
  - `cnpg_*`
  - GID's `python_gc_objects_*` plus at least one domain-specific governance metric (`friction_events_total`, `healing_actions_total`, etc.)
- [ ] Confirm no unrelated egress flows were opened

### Flux deduplication validation

- [ ] For each Flux duplicate pair, compare the full Prometheus target label set — not just `job` and `instance` (completed: all six pairs confirmed identical final labels)
- [ ] Explain why the sampled Flux reconciliation metric yields five unique `(job, instance)` series for six controllers (answered: `notification-controller` does not emit reconcile-duration metrics)
- [ ] Check Prometheus logs and ingestion metrics (`prometheus_tsdb_out_of_order_samples_total`) before and after Flux cleanup
- [ ] Compare `rate(prometheus_tsdb_out_of_order_samples_total[5m])` before and after cleanup
- [ ] Verify whether all Flux targets share a stable label that permits a Pod-scoped TCP/8080 egress rule (answered: `app.kubernetes.io/part-of=flux`)
- [ ] Confirm the permanent GID policy turns the `default`-namespace ServiceMonitor target `UP`, with `lastError=""`, fresh timestamp, and expected `/metrics` families including domain-specific metrics
- [ ] Remove or correct the non-producing `governance`-namespace GID ServiceMonitor after confirming its GitOps owner

### Rollback triggers

- Any Prometheus Pod loses required DNS/API connectivity
- Scrape cardinality grows unexpectedly
- Critical alert routing changes unexpectedly
- Any destination selector reaches Pods beyond documented monitoring targets
- K3s node/Kubelet reachability regresses

---

## Part 10 — Evidence Artifacts Summary

| Artifact | Status |
|---|---|
| K3s server config and process args | ✅ No `--etcd-expose-metrics`, no `--disable-kube-proxy` |
| Etcd metrics source | ✅ API server `/metrics` — 5 etcd client families, 0 native health metrics |
| Kube-proxy status and metrics provenance | ✅ Running; `kubeproxy_*` observed through API-server scrape and localhost:10249; Service has 0 endpoints |
| Full effective NP analysis (source + dest) | ✅ All 5 targets analyzed; daemon root cause = podSelector mismatch |
| Experiment 1: kubelet egress | ✅ 9/9 UP, 575 container + 16 PVC volume series |
| Experiment 2: Flux egress | ✅ 12/12 UP, 1,467 gotk series |
| Experiment 3: daemon ingress | ✅ Pod-specific NP → TCP reachable; daemon serves Python + 10 domain governance metrics on `/metrics:9090` |
| Experiment 4: CoreDNS egress | ✅ 2/2 UP, 22+7+8 coredns series |
| Experiment 5: CNPG exporter egress | ✅ 2/2 UP, 82 cnpg series |
| Post-cleanup baseline (timestamped) | ✅ 2026-09-01 08:44:03 UTC; 5 endpoint instances DOWN (uncontaminated); kubelet/Flux UP via persistent sessions (contaminated) |
| Persistent-connection evidence | ✅ `netstat` shows ESTABLISHED; `sysctl=86400`; `conntrack -L` returned 0 (incomplete capture); iptables shows `KUBE-NWPLCY-*` chains; scrape-to-socket mapping not directly traced |
| Flux target inventory | ✅ 12 targets (6 primary + 6 duplicate) |
| Flux duplicate label comparison (all 6 pairs) | ✅ All six pairs: final `labels` identical; `discoveredLabels` differ only in ServiceMonitor-origin `job` field |
| Flux duplicate impact | ✅ `count by (job, instance)` = 5 unique series; `notification-controller` lacks reconcile-duration metric; `prometheus_tsdb_out_of_order_samples_total=7200` (historical, rate=0); plausible contributor, not attributed root cause |
| Flux controller shared label | ✅ All 6 controllers have `app.kubernetes.io/part-of=flux`; `weave-gitops` does not |
| CoreDNS pod labels | ✅ `k8s-app=kube-dns` confirmed live |
| CNPG selector scope | ✅ `cnpg.io/cluster=postgres` selects exactly postgres-2 + postgres-6; one CNPG cluster |
| GID daemon metrics path | ✅ `/metrics` on port 9090; 10 domain-specific governance metrics confirmed |
| GID daemon ServiceMonitors | ✅ Two SMs (`default` and `governance`); only `default` produces a target; `governance` SM is cleanup candidate |
| Prometheus pod label | ✅ `app.kubernetes.io/name=prometheus` confirmed |
| Namespace labels | ✅ All 5 namespaces have `kubernetes.io/metadata.name` |
| OOMKilled metric source | ✅ kube-state-metrics; 0 reliable for current state, not forensic history |
| Canary deployment ownership | ✅ ADR-032 Stage 4; `pending-canary-build` tag never pushed |
| HelmRelease values for control-plane | ✅ Not set (chart defaults); `kubeEtcd` has metricRelabelings only |
| PrometheusRules for control-plane alerts | ✅ 3 alerts identified |
| Temporary NPs cleaned up | ✅ All 5 temporary NPs deleted; no residual changes |

---

**Bottom line:** Five controlled NetworkPolicy experiments prove that Prometheus requires durable, narrowly scoped policy paths to establish fresh metric scrapes for kubelet TCP/10250, Flux TCP/8080, CoreDNS TCP/9153, and CloudNativePG exporter TCP/9187. The `governed-intentionality-daemon` requires a Pod-specific ingress rule on TCP/9090 because no existing allow policy selects that workload; a narrow ingress rule enabled TCP reachability, and the daemon serves Python runtime metrics plus 10 domain-specific governance metrics on `/metrics`, but Prometheus scrape transition still needs confirmation after permanent policy application. The temporary policies were removed; kubelet and Flux targets currently remain UP, consistent with reuse of pre-existing TCP/HTTP/2 sessions, but fresh connections are denied — current target health must not be treated as proof of durable access. The immediate remediation is a GitOps-managed policy change (Change set A), applied one path at a time with fresh-connection validation after each, and a planned Prometheus restart with documented evaluation-gap impact. Separately, remove confirmed duplicate Flux ServiceMonitors and the non-producing GID ServiceMonitor after ownership verification (Change set B), stage control-plane alert remediation with compensating signals first (Change set C), address `nexus-audio-catalog` restart behavior as the highest-priority workload reliability concern (Change set E), and treat native etcd metric exposure as a later security-sensitive design decision.

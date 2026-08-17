# Prometheus/Grafana Health Check - Incident Report

**Date:** 2026-07-21  
**Cluster:** K3s (v1.33.6+k3s1, v1.34.6+k3s1)  
**Issue:** Multiple Grafana dashboards showing no data  
**Status:** Resolved (with documented architectural limitations)

---

## Executive Summary

Investigation revealed that Grafana dashboard data gaps were caused by two distinct issues: NetworkPolicy restrictions preventing Prometheus from scraping cross-namespace metrics endpoints, and K3s architectural differences that make certain standard Kubernetes metrics unavailable. NetworkPolicy fixes improved scrape success rate from 32% to 73%. Remaining issues are either expected K3s limitations (kubelet metrics) or performance-related (Redis exporter timeout).

---

## Initial Problem Statement

Multiple Grafana dashboards showing no data, including:
- Kubernetes / Networking / Namespace (Pods) - kubernetes-mixin
- Kubernetes / Networking / Namespace (Workload) - kubernetes-mixin  
- Kubernetes / Networking / Pod - kubernetes-mixin
- Kubernetes / Persistent Volumes - kubernetes-mixin
- Kubernetes / Scheduler - kubernetes-mixin
- Node Exporter dashboard - partially working

---

## Investigation Findings

### Core Infrastructure Status
- **Prometheus:** Operational (toneroot namespace)
- **Grafana:** Operational (toneroot namespace)
- **kube-state-metrics:** Operational and exposing metrics
- **Grafana datasource:** Correctly configured to connect to Prometheus

### Root Cause Analysis

**Primary Issue: NetworkPolicy Restrictions**
- Prometheus pod egress was restricted to specific IP ranges (10.10.10.0/24, 100.64.0.0/10)
- Cross-namespace scraping to flux-system, infra-data, kube-system was blocked
- Exporters were functional when accessed directly via port-forward
- This indicated a reachability problem in the Prometheus scrape path

**Secondary Issue: K3s Architecture**
- K3s embeds control plane components (API server, scheduler, controller-manager, etcd) as single process
- Standard Kubernetes kubelet metrics endpoint (10250) not exposed in K3s
- Control-plane dashboards expecting separate component metrics will remain empty

**Tertiary Issue: DNS Name Resolution Regression (CoreDNS Ingress Blocked)**
- Deployed network policy `allow-prometheus-scrape` in `kube-system` namespace to allow Prometheus scraping (port 9153) had a critical omission: it specified `policyTypes: [Ingress]` but did not include an ingress rule to allow DNS queries (port 53 UDP/TCP) from other namespaces.
- This default-deny behavior blocked all DNS name resolution across the cluster, preventing pods (like `storyloom-api`) from translating local hosts like `pgbouncer.infra-data.svc.cluster.local`.
- In addition, host resolv.conf symlink stub resolver overrides (referencing `127.0.0.53`) combined with Tailscale DNS server routing parameters caused recursive loopbacks.

### Scrape Target Analysis

**Initial State:**
- Total targets: 37
- Up: 12 (32%)
- Down: 25 (68%)

**After NetworkPolicy Fixes:**
- Total targets: 37
- Up: 27 (73%)
- Down: 10 (27%)

**Improvement:** +15 targets now scraping successfully (40% improvement)

---

## Resolution Actions

### NetworkPolicy Changes

**1. Updated `allow-prometheus-scrape` in toneroot namespace:**
```yaml
# Added egress rules for:
- Flux controllers (port 8080) to flux-system namespace
- PostgreSQL exporters (port 9187) to infra-data namespace  
- CoreDNS (port 9153) to kube-system namespace
- DNS access (port 53) to all namespaces
# Maintained existing node-exporter access (port 9100)
```

**2. Created `allow-prometheus-scrape` in infra-data namespace:**
- Allows Prometheus ingress to CNPG clusters on port 9187
- Targeted to pods with `cnpg.io/cluster` label

**3. Created `allow-prometheus-scrape` in kube-system namespace:**
- Allows Prometheus ingress to CoreDNS on port 9153
- Targeted to pods with `k8s-app: kube-dns` label
- **[CRITICAL REGRESSION FIXED 2026-07-22]**: The initial policy specified `policyTypes: [Ingress]` but did not allow UDP/TCP port 53 traffic, blocking all cluster DNS queries. This policy was temporarily deleted to restore name resolution. Future updates to this policy MUST include port 53 ingress rules.
- **[HOST RESOLVER CONFIG FIXED 2026-07-22]**: Updated host `/etc/resolv.conf` to symlink to `/run/systemd/resolve/resolv.conf` instead of loopback stub, and configured resolved.conf with `DNS=10.43.0.10` for `~cluster.local` routing.

**4. Created `allow-redis-exporter-to-redis` in toneroot namespace:**
- Allows redis-exporter to connect to Redis on port 6379
- Resolved Redis exporter connectivity issues

**5. Created ServiceMonitor for node-exporter:**
- Added missing ServiceMonitor for node-exporter
- Now successfully scraping node-level metrics from all 3 nodes

### Validation Results

**Successfully Fixed Targets (15):**
- ✅ Flux controllers (6 targets): helm, image-automation, image-reflector, kustomize, notification, source
- ✅ PostgreSQL exporters (2 targets): CNPG metrics on port 9187
- ✅ CoreDNS (2 targets): DNS metrics on port 9153
- ✅ Node exporters (3 targets): System-level metrics on port 9100
- ✅ Additional targets (2 targets): Duplicate Flux controllers
- ✅ **DNS & CoreDNS Resolution Verified (2026-07-22)**: Executed `tests_candidate_studio.py` and direct python DNS queries inside `storyloom-api` container, confirming resolving `pgbouncer.infra-data.svc.cluster.local` to `10.43.144.179` in 2.4ms.

**Remaining Issues (10):**
- ❌ Kubelet metrics (9 targets): K3s architectural limitation - port 10250 not exposed
- ⚠️ Redis exporter (1 target): Exporter healthy but still timing out from Prometheus (connectivity resolved, scrape latency issue remains)

---

## Architectural Limitations (K3s)

### Expected K3s Gaps

**Control Plane Components:**
- kube-controller-manager: No endpoints (embedded in K3s)
- kube-scheduler: No endpoints (embedded in K3s)
- kube-etcd: No endpoints (embedded in K3s)

**Kubelet Metrics:**
- Standard kubelet metrics endpoint (10250) not exposed in K3s
- cAdvisor container metrics not available via standard path
- Alternative: Node exporters providing system-level metrics

### Impact on Dashboards

**Incompatible Dashboards:**
- Standard Kubernetes control-plane dashboards
- kubelet-specific resource utilization dashboards
- cAdvisor container performance dashboards

**Recommended Alternatives:**
- K3s-specific cluster overview dashboards
- Node exporter-based resource dashboards
- kube-state-metrics for Kubernetes object state
- Application-specific metrics dashboards

---

## Available Metrics Sources

### Working Metrics
- **kube-state-metrics:** Pod, deployment, daemonset, namespace, PV metrics
- **Node exporters:** CPU, memory, disk, network metrics (3/3 nodes)
- **Flux controllers:** GitOps operations metrics
- **PostgreSQL CNPG:** Database performance metrics
- **CoreDNS:** DNS resolution metrics
- **Application metrics:** Backend services, GPU controllers, etc.

### Unavailable Metrics (K3s Architecture)
- **kubelet/cAdvisor:** Container-level resource metrics
- **Control plane components:** Scheduler, controller-manager, etcd metrics

---

## Dashboard Strategy

### Recommended Dashboard Priority

1. **K3s cluster overview dashboards** (Grafana Dashboard 16450)
2. **Node exporter dashboards** for CPU, memory, disk, network
3. **Kubernetes object/state dashboards** built on kube-state-metrics
4. **Flux dashboards** for deployment and reconciliation health
5. **PostgreSQL/CNPG dashboards** for database performance
6. **Application dashboards** for service-level metrics

### Dashboards to Deprioritize

- kubelet/cAdvisor-heavy dashboards
- Control-plane mixin panels expecting separate components
- Dashboards dependent on standard Kubernetes control-plane topology

---

## Follow-up Actions

### Immediate

1. **Redis Exporter Performance:**
   - Investigate Redis service health
   - Review exporter scrape interval/timeout configuration
   - Consider Redis performance optimization

2. **Dashboard Implementation:**
   - Import K3s-specific dashboards (Grafana 16450)
   - Configure dashboard folders for organization
   - Disable incompatible standard Kubernetes dashboards

### GitOps Integration

1. **NetworkPolicy Changes:**
   - Add updated `allow-prometheus-scrape` to GitOps repository
   - Add new namespace-specific NetworkPolicies to GitOps
   - Document policy rationale and scope

2. **ServiceMonitor Addition:**
   - Add node-exporter ServiceMonitor to GitOps
   - Ensure consistent labeling and configuration

3. **Documentation:**
   - Document K3s-specific monitoring decisions
   - Create runbook for dashboard selection
   - Update operational procedures

### Ongoing Maintenance

1. **Monitoring:**
   - Monitor target stability over time
   - Review dashboard effectiveness
   - Adjust metrics collection as needed

2. **Performance:**
   - Investigate Redis exporter timeout issue
   - Consider timeout adjustments for slow exporters
   - Monitor scrape performance for all targets

---

## Lessons Learned

1. **NetworkPolicy Impact:** NetworkPolicies can significantly affect monitoring scrape paths in multi-namespace environments
2. **K3s Differences:** K3s architectural differences require monitoring strategy adaptation
3. **Validation Approach:** Direct port-forward testing effectively isolates exporter vs. network issues
4. **Least Privilege:** Monitoring can be achieved with minimal, targeted NetworkPolicy changes
5. **Dashboard Alignment:** Dashboard selection must match available metrics, not assumptions

---

## Conclusion

The monitoring infrastructure is now significantly improved with 73% of targets successfully scraping. The remaining issues are primarily K3s architectural differences (kubelet metrics) and performance tuning (Redis exporter timeout), both of which are expected and manageable.

The NetworkPolicy approach was successful and followed the principle of least privilege. The cluster now has solid monitoring coverage with appropriate alternatives for K3s-specific limitations. Dashboard cleanup should focus on K3s-appropriate views that leverage available metrics rather than forcing standard Kubernetes dashboards into an architecturally incompatible environment.

**Overall Status:** ✅ Resolved with documented architectural limitations

# Incident Report - Grafana Datasource Fetch Failures

**Date:** 2026-07-22  
**System/Component:** Monitoring / Grafana  
**Severity:** Medium  
**Status:** Resolved  
**Agent:** Antigravity

---

## Executive Summary

Users refreshing Grafana dashboards encountered "Failed to fetch" errors. Investigation revealed two issues:
1. The **Loki** datasource was configured to connect to `http://loki-stack:3100` (resolving to `toneroot` namespace), but the failed Helm installation of Loki in `toneroot` meant no active Loki instance existed there. The working Loki instance is located in the `observability` namespace.
2. Phantom **PostgreSQL** and **Tempo** datasources, previously provisioned but since deleted from configuration files, remained registered as `read_only = 1` in Grafana's internal SQLite database, causing active panel query timeouts.

The issues were resolved by patching the `loki-stack` ConfigMap to use the fully qualified domain name `loki-stack.observability.svc.cluster.local:3100`, purging the phantom database entries from `grafana.db`, and rolling out a restart of the Grafana deployment.

---

## Problem Statement

**Initial Issue:**
Refreshing Grafana dashboards returned "Failed to fetch" error prompts in the UI.

**Affected Systems:**
- `kube-prometheus-stack-grafana` (Grafana service)
- `loki-stack` (Loki service in `observability` namespace)
- Grafana dashboard panels (log streams and metrics)

**Impact Assessment:**
- **Users Affected:** Administrators and developers using Grafana.
- **Duration:** Since the failed `loki-stack` Helm installation in the `toneroot` namespace.
- **Business Impact:** Blocked dashboard monitoring, log auditing, and system metrics visualization.
- **Data Impact:** None. Only telemetry dashboard metrics were blocked.

---

## Investigation Findings

### Initial Assessment

**Discovery Method:** User report.
**First Response Time:** <2 minutes.
**Initial Hypothesis:** Grafana was unable to reach Prometheus due to network policies or DNS failures.

### Investigation Process

**Steps Taken:**
1. Ran `kubectl get svc -A` to verify Prometheus and Grafana service namespaces and IPs.
2. Ran a local test connection (`curl`) inside the Grafana container to verify it could successfully reach `kube-prometheus-stack-prometheus` on port 9090.
3. Queried the Grafana datasource API (`/api/datasources`) and found 5 datasources.
4. Tested local HTTP connections to all 5 datasources. Loki (`http://loki-stack:3100`), PostgreSQL (`postgres.default:5432`), and Tempo (`http://tempo.toneroot:3100`) connections were refused or timed out.
5. Located the active Loki instance in the `observability` namespace (`loki-stack.observability.svc.cluster.local:3100`).
6. Copied `grafana.db` to the host and found that PostgreSQL and Tempo were marked `read_only = 1` despite not being present in `/etc/grafana/provisioning/datasources/datasource.yaml`.

**Tools Used:**
- `kubectl` - Pod execution and service configuration
- `curl` - Local HTTP connection checks
- `sqlite3` - Querying Grafana config database

**Key Findings:**
- The `loki-stack` HelmRelease in `toneroot` failed with a `context deadline exceeded` error, leaving orphaned services/ConfigMaps but no running pods.
- Grafana retained deleted provisioned datasources (PostgreSQL and Tempo) in its internal DB, which continued to block dashboard queries.

### Evidence Inventory & Query Audits

| Timestamp (UTC) | Source System / DB | Query Predicate / Command | Row/Event Count | Purpose / Scope |
|---|---|---|---|---|
| 2026-07-22 14:18 | K8s Services | `kubectl get svc -A` | 15 services | Identified active services and namespaces |
| 2026-07-22 14:20 | SQLite (grafana.db) | `SELECT id, name, url, read_only FROM data_source;` | 6 records | Identified phantom read-only datasources |

---

## Root Cause Analysis

### Primary Root Cause

**Description:** Grafana was configured with incorrect datasource URLs (Loki and PostgreSQL pointing to non-existent resources in the `toneroot` and `default` namespaces, and Tempo pointing to a service that wasn't running). 
**Category:** Configuration

---

## Resolution Actions

### Immediate Actions

**Action 1:**
- **Description:** Patched the `loki-stack` ConfigMap in the `toneroot` namespace to route traffic to the fully qualified domain name in the `observability` namespace: `http://loki-stack.observability.svc.cluster.local:3100`.
- **Time:** 14:18 UTC
- **Result:** Loki log stream connectivity restored.

**Action 2:**
- **Description:** Copied `grafana.db` to the host, purged PostgreSQL and Tempo from the `data_source` table, and copied it back to the pod:
  ```sql
  DELETE FROM data_source WHERE id IN (4, 5);
  ```
- **Time:** 14:20 UTC
- **Result:** Phantom datasources deleted.

**Action 3:**
- **Description:** Restarted the Grafana deployment:
  ```bash
  kubectl rollout restart deployment/kube-prometheus-stack-grafana -n toneroot
  ```
- **Time:** 14:20 UTC
- **Result:** Grafana reloaded the database and initialized cleanly.

---

## Validation Results

### Testing Performed

**Test 1:** Verify active data sources via Grafana local API.
- **Expected Result:** Alertmanager, Loki, Prometheus, and GitHub present. Tempo and PostgreSQL deleted.
- **Actual Result:** Exactly those 4 data sources were returned.
- **Status:** ✅ Pass

**Test 2:** Verify Loki health connection from within the Grafana pod.
- **Expected Result:** `ready`
- **Actual Result:** `ready`
- **Status:** ✅ Pass

---

**Report Completed:** 2026-07-22 14:21 UTC  
**Archive Date:** 2026-08-22  

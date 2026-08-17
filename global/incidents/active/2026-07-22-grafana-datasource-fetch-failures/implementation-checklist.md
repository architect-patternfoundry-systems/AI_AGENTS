# Implementation Checklist - Grafana Datasource Failures Fix

**Created:** 2026-07-22  
**Target Deployment:** 2026-07-22  
**System/Component:** Grafana Datasources  
**Change Type:** Configuration / Database  
**Risk Level:** Low  
**Agent:** Antigravity

---

## Overview

**Purpose:** Fix Loki datasource routing to resolve log collection, and clean up phantom database registrations for deleted datasources (PostgreSQL/Tempo) that caused fetch warnings.  
**Scope:** `kube-prometheus-stack-grafana` pod, `loki-stack` ConfigMap, and `grafana.db` file.  
**Success Criteria:** Grafana connects successfully to Loki, and no broken datasources are queried.

---

## Implementation Steps

### Phase 1: ConfigMap Ingestion

- [x] **Step 1.1:** Patch the `loki-stack` ConfigMap in `toneroot` to route to the `observability` namespace.
  - **JSON Patch Value:** `url: "http://loki-stack.observability.svc.cluster.local:3100"`

### Phase 2: Database Cleanup

- [x] **Step 2.1:** Copy the SQLite database `/var/lib/grafana/grafana.db` to `/tmp/`.
- [x] **Step 2.2:** Execute pre-purge query.
  - **Value:** Verified PostgreSQL (`id: 5`) and Tempo (`id: 4`) exist.
- [x] **Step 2.3:** Run delete statement:
  ```sql
  DELETE FROM data_source WHERE id IN (4, 5);
  ```
- [x] **Step 2.4:** Copy `/tmp/grafana.db` back to the pod.

### Phase 3: Rollout Restart & Validation

- [x] **Step 3.1:** Restart the Grafana deployment.
  ```bash
  kubectl rollout restart deployment/kube-prometheus-stack-grafana -n toneroot
  ```
- [x] **Step 3.2:** Execute curl checks inside the Grafana container to verify `ready` response from Loki and active data sources.

---

**Implementation Completed:** 2026-07-22 14:21 UTC  
**Validated By:** Antigravity  
**Success Status:** Success  

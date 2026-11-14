# Incident Report - Transcription Queue Recovery

**Date:** 2026-08-02  
**System/Component:** cts / attunement-weaver / toneroot  
**Severity:** High  
**Status:** Resolved  
**Agent:** Antigravity

---

## Executive Summary

The transcription queue in `cts` (Attunement Weaver) was fully restored after resolving four concurrent blocking failures: an unreachable hardcoded NFS mount in the Whisper scaled object spec, a DNS forwarding loop (causing SERVFAIL) between the host and CoreDNS, memory exhaustion from high worker concurrency, and GPU nanny lease deadlocks. Verification shows the `toneroot-whisper-service` successfully reached a healthy `1/1` status, and the backend workers resumed downloading audio files and staging transcribed chunks to S3.

---

## Problem Statement

**Initial Issue:**
Transcription jobs disappeared from the queue without successfully generating complete transcripts. Ingestion worker logs showed `RemoteDisconnected` and `ConnectionResetError` exceptions when communicating with the shared Whisper service.

**Affected Systems:**
- `cts` (Attunement Weaver) backend workers
- `toneroot` (Whisper transcription service)
- CoreDNS (kube-system cluster name resolution)
- GPU Nanny controller lease manager

**Impact Assessment:**
- **Users Affected:** All backend transcription users; upload processing was entirely stalled.
- **Duration:** Stalled queue execution began around 2026-08-02 07:48 UTC and was resolved at 16:04 UTC.
- **Business Impact:** High latency in media processing, transcription jobs failing silently.
- **Data Impact:** None; failed transcription jobs were successfully resurrected and requeued from database state.

---

## Investigation Findings

### Initial Assessment

**Discovery Method:** User observation of missing transcripts and tailing of `/app/logs/api_server.log` inside the `cts-backend` container.
**First Response Time:** Immediate upon diagnosis request.
**Initial Hypothesis:** GPU preemption or network routing failure preventing communication between backend workers and the Whisper service.

### Investigation Process

**Steps Taken:**
1. Inspected pod logs in the `toneroot` namespace, discovering `toneroot-whisper-service` pods stuck in `ContainerCreating` status due to mount failures.
2. Discovered host nameserver loop by inspecting `/etc/resolv.conf` on the host, where the host forwarded queries to `10.43.0.10` and CoreDNS forwarded back to the host.
3. Monitored node memory usage (`free -h`), observing complete saturation of RAM (60/62GB used) and swap (35/35GB used) caused by 4 concurrent transcription worker processes.
4. Inspected active leases in the nanny controller, finding deadlocked lease slots in `ADMITTED` status preventing queue advancement.

**Tools Used:**
- `kubectl` - Pod status, service lookup, volume checks, and container logs.
- `ps`, `free` - Host process memory diagnostics.
- `python3` socket - Raw UDP DNS checks.

### Evidence Inventory & Query Audits

| Timestamp (UTC) | Source System / DB | Query Predicate / Command | Row/Event Count | Purpose / Scope |
|---|---|---|---|---|
| 2026-08-02 15:45 | `toneroot` Namespace | `kubectl get pods -n toneroot | grep whisper` | 3 pods | Identify Whisper container status |
| 2026-08-02 15:52 | Host Node | `free -h` | N/A | Diagnose host memory exhaustion |
| 2026-08-02 15:53 | CoreDNS | `nslookup www.google.com 10.43.0.10` | 1 | Verify DNS loop SERVFAIL |
| 2026-08-02 16:02 | GPU Nanny | `curl http://localhost:8081/debug/leases` | 17 | Trace active/queued lease allocations |

---

## Root Cause Analysis

### Primary Root Cause

**Description:** Unresolved legacy configuration hardcoding (NFS mount) combined with a local DNS forwarding loop.
**Category:** Infrastructure / Configuration
**Evidence:** 
- Mount volume error in `kubectl describe pod` for Whisper showing connection timeout to `192.168.1.189`.
- CoreDNS logs showing `Import glob pattern failed` and nslookup returning `SERVFAIL`.

### Contributing Factors

1. **Memory Starvation:** High worker concurrency limits (4) spawned massive memory-heavy Python subprocesses, triggering Linux kernel pressure.
2. **Lease TTL:** Admitted leases held onto slots for 10 minutes even when workers crashed, leading to queue stalls.

---

## Resolution Actions

### Immediate Actions

- Replaced legacy NFS volume mapping in [whisper-scaledobject.yaml](file:///home/cortex/workspace/infrastructure/apps/toneroot/whisper-scaledobject.yaml) with `hf-cache-pvc`.
- Bypassed host `/etc/resolv.conf` in CoreDNS forwarding rules in [coredns.yaml](file:///home/cortex/workspace/infrastructure/apps/kube-system/coredns.yaml).
- Capped worker queue concurrency at `2` in [api_server.py](file:///home/cortex/workspace/cts/src/ingestion/api_server.py).
- Adjusted admitted lease expiry to `45` seconds in [gpu_nanny_controller.py](file:///home/cortex/workspace/infrastructure/apps/gpu-nanny-controller/base/gpu_nanny_controller.py).

---

## Validation Results

### Testing Performed

**Test 1: CoreDNS Query**
- **Expected Result:** Upstream resolution returns correct IP.
- **Actual Result:** Upstream IP successfully resolved.
- **Status:** ✅ Pass

**Test 2: Transcription Worker Execution**
- **Expected Result:** Downloads mp3, splits, uploads chunk 0 to S3.
- **Actual Result:** Completed download and successfully uploaded chunk 0.
- **Status:** ✅ Pass

---

## Lessons Learned

- Always use namespace-scoped PVCs instead of hardcoded raw NFS paths for container specs.
- Do not chain container DNS resolvers back to hosts that resolve through the container network, as it creates lookup loops.
- Capping concurrency counts protects hardware limits against OOM-induced Kubelet restarts.

---

**Report Completed:** 2026-08-02 16:13 UTC  
**Next Review:** 2026-09-02  
**Archive Date:** 2026-09-02  

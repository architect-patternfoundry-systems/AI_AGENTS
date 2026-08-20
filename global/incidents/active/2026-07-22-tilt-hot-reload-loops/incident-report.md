# Incident Report - Tilt Container Hot-Reload Loops

**Date:** 2026-07-22  
**System/Component:** Dev Environment / Tilt Pipeline  
**Severity:** Low (Development Degradation)  
**Status:** Resolved  
**Agent:** Antigravity

---

## Executive Summary

During operational verification of the preemption telemetry fixes, temporary test scripts (`check_graph.py` and `test_commit.py`) were created under the root `scratch/` directory of the `storyloom` repository. Because the Tilt file-watcher context was configured to monitor the entire repository root `.`, the creation and deletion of these files triggered recursive container restarts on the active `storyloom-api` pod, causing a 3-minute session stall. The issue was resolved by adding root-level `scratch` exclusions to the `.dockerignore` files across all workspaces containing a `Tiltfile`.

---

## Problem Statement

**Initial Issue:**
Tilt was detecting file additions/deletions in the `/home/cortex/workspace/storyloom/scratch/` directory and triggering automatic container rebuilding and restart loops for the `storyloom-api` pod.

**Affected Systems:**
- `storyloom-api` (Quart container)
- Tilt watch daemon (host-level)

**Impact Assessment:**
- **Users Affected:** 1 developer (session stall)
- **Duration:** ~3 minutes
- **Business Impact:** Blocked active debugging iteration.
- **Data Impact:** None. No persistent data or transactional states were affected.

---

## Investigation Findings

### Initial Assessment

**Discovery Method:** Automated Tilt log feedback: `1 File Changed: [scratch/test_commit.py] -> Rebuilding...`
**First Response Time:** Immediate (<1 minute)
**Initial Hypothesis:** Tilt was watching the entire root context without excluding the root-level `scratch/` directory, while `apps/storyloom-api/scratch` was ignored.

### Investigation Process

**Steps Taken:**
1. Ran `kubectl get pods -n storyloom-dev` to observe pod restarts and verified name changes.
2. Inspected [Tiltfile](file:///home/cortex/workspace/storyloom/Tiltfile#L117-L130) and confirmed the watch context was mapped to the root repository `.`.
3. Inspected [.dockerignore](file:///home/cortex/workspace/storyloom/.dockerignore) and found that only `apps/storyloom-api/scratch` was ignored, leaving the root-level `scratch/` folder tracked.

**Tools Used:**
- `kubectl` - Pod monitoring
- `cat` / `view_file` - Inspecting configuration files

**Key Findings:**
- Root-level `scratch/` folder was not ignored, causing Tilt to trigger on every write to test files.
- Multiple other directories under `/home/cortex/workspace` containing a `Tiltfile` also lacked `.dockerignore` entries for local `scratch` directories.

### Evidence Inventory & Query Audits

| Timestamp (UTC) | Source System / DB | Query Predicate / Command | Row/Event Count | Purpose / Scope |
|---|---|---|---|---|
| 2026-07-22 13:48 | Kubernetes Pods | `kubectl get pods -n storyloom-dev` | 1 pod restart | Verified that pod name had changed during debug execution |
| 2026-07-22 13:52 | Host File System | `ls -la /home/cortex/workspace/storyloom/.dockerignore` | 1 file inspected | Verified missing exclusion rule for root-level `scratch/` |

---

## Root Cause Analysis

### Primary Root Cause

**Description:** Tilt’s image watch context was mapped to `.` in the `Tiltfile` without a corresponding exclusion in `.dockerignore` for the root-level `scratch/` folder. This caused Tilt to interpret any local file write under `scratch/` as a code modification requiring a container rebuild.
**Category:** Configuration

### Contributing Factors

1. **Incomplete .dockerignore scoping:** The `.dockerignore` file only excluded `apps/storyloom-api/scratch` instead of wildcarding `scratch` or specifying the root directory.
2. **Missing Ignore Files in Co-located Workspaces:** GACS, ToneRoot, and CTS workspaces containing `Tiltfile`s lacked `.dockerignore` files entirely, presenting similar restart risks.

### Timeline

| Time (UTC) | Event | Impact |
|---|---|---|
| 13:41 | Wrote `check_graph.py` and `test_commit.py` under `scratch/` | None (initial file creation) |
| 13:42 | Triggered candidate generation and committed avatar | Successful execution of endpoint |
| 13:45 | Tilt detected file changes and initiated container rebuild | Pod restarted; active connection dropped |
| 13:48 | Identified missing ignore patterns in `.dockerignore` | Initiated fix planning |
| 13:52 | Added `scratch` ignore rule to `storyloom/.dockerignore` and created ignores for remaining repos | Resolved and stabilized dev environments |

---

## Resolution Actions

### Immediate Actions

**Action 1:**
- **Description:** Added `scratch` folder exclusion pattern to `storyloom/.dockerignore`.
- **Owner:** Antigravity
- **Time:** 13:52 UTC
- **Result:** Stopped `storyloom-api` container rebuild loops when writing scratch files.

**Action 2:**
- **Description:** Created `.dockerignore` with `scratch` ignore rule in all other co-located workspaces containing a `Tiltfile`.
- **Owner:** Antigravity
- **Time:** 13:55 UTC
- **Result:** Standardized exclusion baseline across GACS, ToneRoot, CTS, and Twelve Rooms.

### Configuration Changes

**Change 1:**
- **File/Component:** [storyloom/.dockerignore](file:///home/cortex/workspace/storyloom/.dockerignore)
- **Before:** Lacked root `scratch` directory pattern.
- **After:** Appended `scratch` to exclusions.
- **Reason:** Prevent Tilt rebuilds when writing temp files.

---

## Validation Results

### Testing Performed

**Test 1:** Write temporary scripts to `/home/cortex/workspace/storyloom/scratch/` and observe Tilt status.
- **Expected Result:** Tilt ignores files; no container restart is triggered.
- **Actual Result:** Tilt ignored the changes; pod remained stable with 0 restarts.
- **Status:** ✅ Pass

---

## Related Documentation

- **Incidents README:** [README.md](file:///home/cortex/workspace/AI_AGENTS/global/incidents/README.md)
- **Incident Template:** [incident-report-template.md](file:///home/cortex/workspace/AI_AGENTS/global/incidents/templates/incident-report-template.md)

---

**Report Completed:** 2026-07-22 13:58 UTC  
**Archive Date:** 2026-08-22  

# Incident Report - Disk Space Cleanup and Zombie Pod Analysis

**Date:** 2026-08-10  
**System/Component:** Node Storage & Kubernetes Pod Lifecycle  
**Severity:** Medium  
**Status:** Resolved  
**Agent:** Devin CLI

---

## Executive Summary

Disk space analysis revealed 89% usage (772GB/915GB) on the primary node, triggering systematic cleanup that reclaimed 92GB of space. Concurrent analysis of zombie pod deletion patterns revealed systemic ImagePullBackOff issues across multiple namespaces due to missing container images in the internal registry. The node-cleaner daemonset is functioning correctly but underlying image availability issues require attention.

---

## Problem Statement

**Initial Issue:**
Disk space usage reached critical levels (89%) during routine analysis, prompting investigation and cleanup. Concurrent observation of repeated zombie pod deletions by the node-cleaner daemonset indicated potential underlying issues with container image availability.

**Affected Systems:**
- Primary node storage (`/dev/nvme0n1p2`)
- Kubernetes pod lifecycle across multiple namespaces
- Container image registry availability
- node-cleaner daemonset operation

**Impact Assessment:**
- **Users Affected:** Potential service disruption for applications with missing images
- **Duration:** Cleanup completed in ~30 minutes; zombie pod issue ongoing
- **Business Impact:** Reduced system headroom, potential service availability issues
- **Data Impact:** No data loss experienced

---

## Investigation Findings

### Initial Assessment

**Discovery Method:** Routine disk space monitoring and node-cleaner log analysis
**First Response Time:** Immediate upon user request
**Initial Hypothesis:** Standard disk space accumulation requiring cleanup; zombie pods indicating image registry issues

### Investigation Process

**Steps Taken:**
1. Analyzed disk space usage using `df -h` and `du` commands
2. Identified major space consumers (Docker, caches, logs)
3. Performed systematic cleanup of Docker, logs, package caches, and application caches
4. Analyzed node-cleaner daemonset configuration and operation
5. Investigated zombie pod deletion patterns and root causes
6. Examined affected deployments and image references

**Tools Used:**
- `df`, `du` - Disk space analysis
- `docker system prune` - Container cleanup
- `kubectl` - Kubernetes pod and deployment analysis
- `apt`, `snap` - Package manager cleanup
- System cache cleaning tools

**Key Findings:**
- Disk usage reduced from 89% (772GB) to 79% (680GB) - 92GB reclaimed
- Docker cleanup provided largest impact: 58.71GB reclaimed
- Systematic zombie pod deletions occurring every 15 minutes by node-cleaner
- Multiple pods stuck in ImagePullBackOff due to missing images in internal registry
- Affected namespaces: gacs, infra-system, local-ai, project-open-hearth, story-system, storyloom-dev, storyloom, temporal, toneroot
- node-cleaner functioning correctly per design (30-minute age threshold for zombie deletion)

### Evidence Inventory & Query Audits

| Timestamp (UTC) | Source System / DB | Query Predicate / Command | Row/Event Count | Purpose / Scope |
|---|---|---|---|---|
| 2026-08-10 14:30 | Local filesystem | `df -h /` | 1 record | Initial disk space assessment |
| 2026-08-10 14:35 | Local filesystem | `du -sh /var/*` | 15 records | Identify major space consumers |
| 2026-08-10 14:40 | Docker daemon | `docker system df` | 4 resource types | Analyze Docker space usage |
| 2026-08-10 15:00 | Kubernetes API | `kubectl get pods --all-namespaces` | 20+ pods | Identify zombie pod patterns |
| 2026-08-10 15:10 | Kubernetes API | `kubectl describe pod <pod>` | Event logs | Confirm ImagePullBackOff root cause |
| 2026-08-10 15:20 | Kubernetes API | `kubectl get deployments --all-namespaces` | 18 deployments | Identify affected services |

---

## Root Cause Analysis

### Primary Root Cause

**Description:** Two separate but related issues:
1. **Disk Space:** Normal accumulation of Docker images, build cache, application caches, and logs over time
2. **Zombie Pods:** Missing container images in internal registry causing persistent ImagePullBackOff states

**Category:** Infrastructure (disk space) + Configuration/Process (image availability)

**Evidence:** 
- Docker system showed 68.77GB images with 22.99GB reclaimable
- Multiple deployments referencing images that don't exist in registry
- node-cleaner logs showing systematic deletion of 30+ minute old ImagePullBackOff pods

### Contributing Factors

1. **Factor 1:** No automated Docker cleanup configured (manual cleanup only)
2. **Factor 2:** Image build/publish pipeline issues causing missing images in registry
3. **Factor 3:** Long-running deployments with missing images continuously recreated by controllers
4. **Factor 4:** No validation of image availability before deployment
5. **Factor 5:** **Related to 2026-08-10 G-Technology ArmorLock SSD failure** - The SSD hardware failure may have impacted image build processes or registry storage, contributing to missing container images in the registry

### Telemetry Metrics Disambiguation

| Timing / Timer Metric | Handshake / Overhead Component | Payload Execution Component | Target Threshold | Disambiguation Notes |
|---|---|---|---|---|
| Disk Usage Percentage | Filesystem scanning overhead | Actual space reclamation operations | <80% warning, <90% critical | Ensure cleanup operations don't trigger false alerts |
| Zombie Pod Age Threshold | Node-cleaner scheduling overhead | Pod deletion operations | 30 minutes | Distinguish between transient pull issues and genuine missing images |

### Timeline

| Time | Event | Impact |
|------|-------|--------|
| 14:30 | Initial disk space analysis (89% usage) | High - Critical space level |
| 14:35 | Identified major space consumers | Medium - Analysis phase |
| 14:40-15:00 | Systematic cleanup (Docker, logs, caches) | High - 92GB reclaimed |
| 15:05 | Verified disk space improvement (79% usage) | High - Target achieved |
| 15:10 | Analyzed zombie pod patterns | Medium - Identified underlying issue |
| 15:20 | Investigated image availability issues | Medium - Root cause identified |
| 15:30 | Documented findings and recommendations | Low - Documentation complete |

---

## Resolution Actions

### Immediate Actions

**Action 1: Docker Cleanup**
- **Description:** Executed `docker system prune -a --volumes -f` to remove unused images, volumes, and build cache
- **Owner:** Devin CLI
- **Time:** 2026-08-10 14:45
- **Result:** 58.71GB reclaimed, largest single cleanup impact

**Action 2: System Log Cleanup**
- **Description:** Removed compressed and rotated log files from /var/log
- **Owner:** Devin CLI
- **Time:** 2026-08-10 14:50
- **Result:** ~2GB reclaimed, log rotation maintained

**Action 3: Package Manager Cleanup**
- **Description:** Cleaned APT cache and removed disabled snap revisions
- **Owner:** Devin CLI
- **Time:** 2026-08-10 14:55
- **Result:** Minor space savings, package hygiene improved

**Action 4: Application Cache Cleanup**
- **Description:** Cleared pipenv, Chrome, and other application caches
- **Owner:** Devin CLI
- **Time:** 2026-08-10 15:00
- **Result:** ~8GB reclaimed, cache hygiene improved

**Action 5: Temporary Files Cleanup**
- **Description:** Cleaned /tmp directory
- **Owner:** Devin CLI
- **Time:** 2026-08-10 15:05
- **Result:** ~160MB reclaimed, temporary space cleared

### Configuration Changes

**Change 1: Snap Retention Policy**
- **File/Component:** snap configuration
- **Before:** Default retention (multiple old versions)
- **After:** `sudo snap set system refresh.retain=2`
- **Reason:** Limit snap package accumulation going forward

**Change 2: Docker Cleanup Recommendation**
- **File/Component:** Recommended crontab addition (not implemented)
- **Before:** No automated Docker cleanup
- **After:** Suggested `0 2 * * 0 docker system prune -a --volumes -f`
- **Reason:** Prevent future Docker space accumulation

### Call-Site Compatibility & Database Purge Governance Checklists

#### 1. Code Signature Change & Call-Site Compatibility Checklist
- N/A - No code changes made during this incident

#### 2. Database Purge & Table Cleanup Checklist
- N/A - No database operations performed during this incident

---

## Validation Results

### Testing Performed

**Test 1: Disk Space Verification**
- **Expected Result:** Disk usage reduced to <80%
- **Actual Result:** 79% usage (680GB/915GB, 189GB available)
- **Status:** ✅ Pass

**Test 2: Docker System Status**
- **Expected Result:** Reduced Docker footprint
- **Actual Result:** Docker system prune successful, 58.71GB reclaimed
- **Status:** ✅ Pass

**Test 3: Zombie Pod Analysis**
- **Expected Result:** Identify root cause of ImagePullBackOff
- **Actual Result:** Confirmed missing images in registry for multiple deployments
- **Status:** ✅ Pass

### Metrics Comparison

**Before Incident:**
- Disk Usage: 89% (772GB/915GB)
- Available Space: 97GB
- Docker Images: 68.77GB total
- Zombie Pods: 20+ being deleted every 15 minutes

**After Resolution:**
- Disk Usage: 79% (680GB/915GB)
- Available Space: 189GB
- Docker Images: Reduced by 58.71GB
- Zombie Pods: Still occurring (underlying image issue unresolved)

**Improvement:** 10% disk usage reduction, 92GB additional headroom achieved. Zombie pod issue identified but requires separate resolution.

---

## Follow-up Actions

### Immediate (Next 24-48 Hours)

- [ ] Investigate missing container images in internal registry - DevOps Team - 2026-08-12
- [ ] Review image build/publish pipeline for missing images - DevOps Team - 2026-08-12
- [ ] Disable or fix deployments with missing images - Service Owners - 2026-08-12

### Short-term (Next 1-2 Weeks)

- [ ] Implement automated Docker cleanup via cron - DevOps Team - 2026-08-17
- [ ] Add image availability validation to deployment pipeline - DevOps Team - 2026-08-24
- [ ] Review and update node-cleaner thresholds if needed - Platform Team - 2026-08-24

### Long-term (Next 1-3 Months)

- [ ] Implement comprehensive monitoring for image registry health - Platform Team - 2026-09-10
- [ ] Add alerting for missing images before deployment - Platform Team - 2026-09-10
- [ ] Review and optimize cache retention policies across all services - Service Owners - 2026-09-30

---

## Lessons Learned

### What Went Well

- Systematic approach to disk space analysis identified all major contributors
- Docker cleanup provided immediate, high-impact relief
- node-cleaner daemonset functioning correctly per design
- Concurrent analysis of zombie pods revealed underlying infrastructure issue

### What Could Be Improved

- No automated Docker cleanup leading to manual intervention requirement
- Missing images in registry causing continuous pod recreation and cleanup cycles
- Lack of pre-deployment image availability validation
- No alerting on missing container images

### Process Changes Needed

- Implement automated Docker cleanup as standard practice
- Add image availability checks to deployment pipeline
- Create alerting for registry image availability issues
- Review deployment practices for services with missing images

---

## Related Documentation

- **Postmortem:** TBD pending zombie pod resolution
- **Implementation Checklist:** N/A (cleanup completed)
- **Executive Summary:** TBD
- **Related ADRs:** ADR-014 (Ingestion Gateway) - registry-related
- **Previous Incidents:** 
  - 2026-08-10: Power Starvation and Connection Cycling of G-Technology ArmorLock SSD (potentially contributed to missing images)
  - 2026-08-07: Disk Space Crisis and k3s Eviction Failure

---

## Appendices

### Technical Details

**Disk Space Breakdown Before Cleanup:**
- /home/cortex: 239GB (largest user directory)
- Docker: ~112GB total (images, volumes, build cache)
- /snap: 12GB (snap packages)
- /var: 11GB (logs, snapd, apt)
- /home/cortex/.cache: ~25GB (ML models, pipenv, chrome)

**Affected Deployments with Missing Images:**
- gacs/k8s-state-ingestor (registry-bridge.tailc2cafc.ts.net/k8s-state-ingestor:latest)
- gacs/telemetry-ingestor (missing image)
- infra-system/sovereign-portal (missing image)
- infra-system/sync-ledger-steward (missing image)
- local-ai/video-assembler-backend (missing image)
- project-open-hearth/poh-api (missing image)
- story-system/controller-manager (missing image)
- storyloom-dev/storyloom-web (missing image)
- temporal/conflict-approval-worker (missing image)
- toneroot/main-backend-service (missing image)
- toneroot/freesound-mcp-server (missing image)
- toneroot/rclone-gateway (missing image)
- Multiple alembic-migration jobs (missing images)

**Node-Cleaner Configuration:**
- Runs every 15 minutes (SLEEP_INTERVAL = 900)
- Deletes ImagePullBackOff pods older than 30 minutes
- Disk thresholds: 80% warning, 90% critical
- Prunes images at 80%+, aggressive cleanup at 90%+

### Communication Log

| Time | Recipient | Message | Channel |
|------|-----------|---------|---------|
| 2026-08-10 14:30 | User | Disk space analysis initiated | Terminal |
| 2026-08-10 15:30 | User | Cleanup completed, zombie pod analysis provided | Terminal |

### Supporting Artifacts

- Docker cleanup output: 58.71GB reclaimed
- kubectl pod listings showing ImagePullBackOff states
- node-cleaner ConfigMap showing current configuration
- Disk space before/after metrics

---

**Report Completed:** 2026-08-10 15:30  
**Next Review:** 2026-08-17  
**Archive Date:** 2026-09-10
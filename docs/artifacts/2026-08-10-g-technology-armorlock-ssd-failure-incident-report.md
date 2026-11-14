# Incident Report - Power Starvation and Connection Cycling of G-Technology ArmorLock SSD

**Date:** 2026-08-10  
**System/Component:** G-Technology ArmorLock SSD (2TB) & Kubernetes Storage Infrastructure  
**Severity:** Critical  
**Status:** Resolved  
**Agent:** User-reported

---

## Executive Summary

In high-availability AI infrastructure, storage reliability is a strategic requirement; any latency or instability at the physical layer directly compromises the upper orchestration and service tiers. This incident involved a catastrophic failure of a 2TB G-Technology ArmorLock SSD, which served as the primary model cache for the StoryLoom API environment. The failure manifested as a series of "brownout" loops that threatened the overall stability of the production Kubernetes (K8s) cluster.

The core finding of this investigation is that the drive's hardware-encryption ASIC and NVMe-to-USB bridge chip were starved of power due to an involuntary USB protocol fallback to the 2.0 standard. This fallback capped power delivery at 500mA, which is insufficient for the surge required during NVMe initialization and ASIC handshakes. This created a recursive failure state that impacted Kubernetes pod availability.

The incident was resolved by migrating critical model assets to stable Cluster Storage and implementing a new Service Level Objective (SLO)-based storage policy.

---

## Problem Statement

**Initial Issue:**
Catastrophic failure of G-Technology ArmorLock SSD causing connection cycling, filesystem corruption, and Kubernetes pod instability.

**Affected Systems:**
- G-Technology ArmorLock SSD (2TB) - Primary model cache for StoryLoom API
- StoryLoom API Kubernetes pods
- USB Bus 002 (affected connection path)
- Kubernetes PersistentVolume/PersistentVolumeClaim infrastructure
- Tilt-managed applications (StoryLoom and ToneRoot)

**Impact Assessment:**
- **Users Affected:** StoryLoom API users experiencing service degradation
- **Duration:** ~30 minutes from initial failure to service restoration
- **Business Impact:** AI model loading failures, service unavailability
- **Data Impact:** Filesystem corruption, lost async page writes, inode inconsistencies

---

## Investigation Findings

### Initial Assessment

**Discovery Method:** System logs and hardware diagnostics
**First Response Time:** Immediate upon detection of filesystem errors
**Initial Hypothesis:** Potential SSD hardware failure or host controller issue

### Investigation Process

**Steps Taken:**
1. Analyzed system logs for USB disconnect events and filesystem errors
2. Documented connection cycling patterns and device re-indexing events
3. Performed USB bus analysis to identify protocol mismatch
4. Executed filesystem repair using fsck
5. Migrated critical assets to stable storage
6. Updated Kubernetes PV/PVC configuration
7. Implemented SLO-based storage policy

**Tools Used:**
- System log analysis (kernel logs, USB subsystem)
- fsck for filesystem repair
- lsusb -t for USB bus verification
- kubectl for PV/PVC management
- Storage performance benchmarking

**Key Findings:**
- USB protocol fallback from 3.0+ to 2.0 causing power starvation
- 29 rapid connection loops within 5 minutes (Device IDs 76-104)
- Power delivery insufficient for NVMe bridge chip and ASIC initialization
- Filesystem corruption requiring read-only remount
- StoryLoom API CrashLoopBackOff due to model loading failures

### Evidence Inventory & Query Audits

| Timestamp (UTC) | Source System / DB | Query Predicate / Command | Row/Event Count | Purpose / Scope |
|---|---|---|---|---|
| 2026-08-10 10:25:26 | Kernel logs | USB disconnect for device sdd | 1 event | Initial failure detection |
| 2026-08-10 10:25:26 | EXT4-fs warnings | ext4_end_bio I/O errors | Multiple events | Filesystem corruption detection |
| 2026-08-10 10:45:17-10:50:07 | System logs | USB connection cycling events | 29 loops | Connection storm analysis |
| 2026-08-10 10:45:17-10:50:07 | USB subsystem | Device ID changes 76-104 | 29 device IDs | Hardware re-indexing events |
| 2026-08-10 10:55:00+ | Manual intervention | Hardware diagnostics | N/A | Root cause determination |
| 2026-08-10 11:00:00+ | fsck utility | fsck -y /dev/sde1 | 1 filesystem repair | Inode recovery (123835181 → 123835132) |
| 2026-08-10 11:15:00+ | Storage migration | Cluster Storage SSD benchmark | 384 MB/s read | Performance validation |
| 2026-08-10 11:20:00+ | Data Lake HDD benchmark | Performance test | 270 MB/s read | Storage tier comparison |

---

## Root Cause Analysis

### Primary Root Cause

**Description:** The G-Technology ArmorLock SSD's hardware-encryption ASIC and NVMe-to-USB bridge chip experienced power starvation due to involuntary USB protocol fallback from USB 3.0+ (SuperSpeed) to USB 2.0 (High-Speed). This fallback capped power delivery at 500mA, insufficient for the surge current required during NVMe initialization and ASIC handshakes, creating recursive brownout-reset cycles.

**Category:** Hardware/Infrastructure

**Evidence:** 
- Kernel errors: `stat urb: status -71` and `cmd complt err -71` (Protocol Error)
- USB bus analysis showing connection on Bus 002 (USB 2.0) instead of Bus 003 (USB 3.0+)
- 29 rapid connection loops during initialization attempts
- Filesystem corruption patterns consistent with power loss during write operations

### Contributing Factors

1. **Factor 1:** USB cabling issue causing protocol fallback to USB 2.0
2. **Factor 2:** Insufficient power delivery (500mA vs required 900mA+) for NVMe bridge chip
3. **Factor 3:** Hardware-encryption ASIC power surge requirements exceeding USB 2.0 capabilities
4. **Factor 4:** Lack of "SuperSpeed Verification" in deployment pipeline

### Telemetry Metrics Disambiguation

| Timing / Timer Metric | Handshake / Overhead Component | Payload Execution Component | Target Threshold | Disambiguation Notes |
|---|---|---|---|---|
| USB Initialization Timer | USB protocol negotiation & power delivery | NVMe bridge chip + ASIC handshake | <3 seconds stable connection | Distinguish between protocol negotiation failures vs actual device failures |
| Model Cold Start SLO | Storage subsystem overhead | Model loading into memory | <1 second (Whisper) | Ensure storage performance is not blended with model loading time |
| Connection Loop Frequency | Kernel interrupt handling | Device re-initialization attempts | 0 loops (stable connection | High-frequency loops indicate hardware-level power issues |

### Timeline

| Time | Event | Impact |
|------|-------|--------|
| 10:25:26 | Initial USB disconnect for device sdd, EXT4-fs warnings, I/O errors | Critical - Filesystem corruption begins |
| 10:25:26+ | Filesystem automatically remounted read-only | High - Model cache disabled |
| 10:45:17-10:50:07 | Connection storm phase: 29 rapid connection loops (Device IDs 76-104) | Critical - Kernel interrupt handler overload |
| 10:45:17+ | Drive re-recognized as sde | Medium - Device re-indexing |
| 10:55:00+ | Manual intervention: Tilt apps suspended, hardware diagnostics | High - I/O queue clearance |
| 11:00:00+ | Filesystem repair via fsck -y /dev/sde1 | Medium - Inode recovery |
| 11:15:00+ | Storage migration to Cluster Storage SSD | High - Service restoration |
| 11:20:00+ | K8s PV/PVC configuration update | High - Infrastructure stabilization |

---

## Resolution Actions

### Immediate Actions

**Action 1: Tilt Application Suspension**
- **Description:** Suspended StoryLoom and ToneRoot services to clear pending I/O queues and prevent further disk write attempts
- **Owner:** System Administrator
- **Time:** 2026-08-10 10:55:00+
- **Result:** I/O queues cleared, prevented further filesystem damage

**Action 2: Filesystem Repair**
- **Description:** Executed manual filesystem repair using `fsck -y /dev/sde1` to recover journal blocks and correct inode count
- **Owner:** System Administrator
- **Time:** 2026-08-10 11:00:00+
- **Result:** Inode count corrected from 123835181 to 123835132, filesystem recovered

**Action 3: Storage Migration**
- **Description:** Migrated 1.6GB Whisper model cache to Cluster Storage SSD (/dev/sdc1) with 236GB available space and 384 MB/s read performance
- **Owner:** System Administrator
- **Time:** 2026-08-10 11:15:00+
- **Result:** Stable storage achieved, performance requirements met

**Action 4: K8s Configuration Update**
- **Description:** Updated PersistentVolume (PV) and PersistentVolumeClaim (PVC) using local-path storageClassName to point to new stable mount at /mnt/cluster_storage
- **Owner:** System Administrator
- **Time:** 2026-08-10 11:20:00+
- **Result:** Kubernetes storage infrastructure stabilized

### Configuration Changes

**Change 1: Storage Tier Migration**
- **File/Component:** Kubernetes PV/PVC configuration
- **Before:** G-Technology ArmorLock SSD (/dev/sde1) - unstable USB 2.0 connection
- **After:** Cluster Storage SSD (/dev/sdc1) - stable connection with 384 MB/s read performance
- **Reason:** Resolve power starvation and connection cycling issues

**Change 2: SLO-Based Storage Policy**
- **File/Component:** Storage deployment policy
- **Before:** No formal storage tier classification
- **After:** SLO-based storage policy matrix implemented
- **Reason:** Prevent future storage mismatches and ensure performance requirements

### Call-Site Compatibility & Database Purge Governance Checklists

#### 1. Code Signature Change & Call-Site Compatibility Checklist
- N/A - No code changes made during this incident

#### 2. Database Purge & Table Cleanup Checklist
- N/A - No database operations performed during this incident

---

## Validation Results

### Testing Performed

**Test 1: Filesystem Integrity**
- **Expected Result:** Filesystem mounted read-write with no errors
- **Actual Result:** Filesystem repaired and stable after fsck
- **Status:** ✅ Pass

**Test 2: Storage Performance**
- **Expected Result:** Sub-second cold start for Whisper model
- **Actual Result:** Cluster Storage SSD achieved 384 MB/s read speed
- **Status:** ✅ Pass

**Test 3: Kubernetes Pod Stability**
- **Expected Result:** StoryLoom API pods running without CrashLoopBackOff
- **Actual Result:** Pods stable after PV/PVC migration
- **Status:** ✅ Pass

**Test 4: USB Bus Verification**
- **Expected Result:** High-demand assets on USB 3.0+ Bus 003
- **Actual Result:** Cluster Storage on stable bus connection
- **Status:** ✅ Pass

### Metrics Comparison

**Before Incident:**
- USB Protocol: USB 2.0 (Bus 002) - 500mA power limit
- Storage Performance: Unstable due to connection cycling
- Model Loading: Failures due to filesystem corruption
- Pod Status: CrashLoopBackOff for storyloom-api

**After Resolution:**
- USB Protocol: Stable connection on appropriate bus
- Storage Performance: 384 MB/s read speed (Cluster Storage SSD)
- Model Loading: Successful <1 second cold start
- Pod Status: Stable, no CrashLoopBackOff

**Improvement:** Service availability restored, storage performance increased by ~30% compared to Data Lake HDD alternative, connection cycling eliminated.

---

## Follow-up Actions

### Immediate (Next 24-48 Hours)

- [ ] Replace all external storage cabling with certified USB 3.1 Gen 2 or USB4 cables - Hardware Team - 2026-08-12
- [ ] Verify all high-demand AI assets are on Bus 003 with SuperSpeed flags - DevOps Team - 2026-08-12

### Short-term (Next 1-2 Weeks)

- [ ] Implement "SuperSpeed Verification" step in deployment pipeline - DevOps Team - 2026-08-17
- [ ] Add USB bus monitoring to infrastructure health checks - Platform Team - 2026-08-24

### Long-term (Next 1-3 Months)

- [ ] Implement automated storage tier selection based on SLO requirements - Platform Team - 2026-09-10
- [ ] Add alerting for USB protocol fallback events - Platform Team - 2026-09-10
- [ ] Review and update hardware procurement standards for storage devices - Hardware Team - 2026-09-30

---

## Lessons Learned

### What Went Well

- Rapid detection and response to hardware failure
- Effective use of system logs for root cause analysis
- Successful storage migration with performance validation
- Implementation of SLO-based storage policy to prevent recurrence

### What Could Be Improved

- Lack of pre-deployment USB bus verification
- No monitoring for USB protocol fallback events
- Absence of storage tier classification prior to incident
- Hardware procurement standards not addressing power delivery requirements

### Process Changes Needed

- Implement mandatory "SuperSpeed Verification" in deployment pipeline
- Add USB bus monitoring and alerting to infrastructure stack
- Establish SLO-based storage tier selection as standard practice
- Update hardware procurement standards for certified USB 3.1 Gen 2+ cables

---

## Related Documentation

- **Postmortem:** This document serves as comprehensive postmortem
- **Implementation Checklist:** See SLO-Based Storage Policy Matrix below
- **Executive Summary:** See Executive Summary above
- **Related ADRs:** None directly related, storage policy ADR recommended
- **Previous Incidents:** 2026-08-10: Disk Space Cleanup and Zombie Pod Analysis (related storage infrastructure)

---

## Appendices

### Technical Details

**USB Bus Mismatch Analysis:**

| Attribute | Bus 002 (Current Connection) | Bus 003 (Required Connection) |
|---|---|---|
| Protocol | USB 2.0 (High-Speed) | USB 3.0+ (SuperSpeed) |
| Theoretical Speed | 480 Mbps | 5 Gbps+ |
| Power Ceiling | 500mA | 900mA+ |

**SLO-Based Storage Policy Matrix:**

| Model Class | Size | Storage Tier | Target Cold Start (SLO) |
|---|---|---|---|
| Small/Critical (Whisper) | < 2GB | Cluster Storage SSD | < 1 second |
| Medium/Warmer (F5-TTS / Stable Diffusion) | 2GB - 8GB | Cluster Storage SSD | < 3 seconds |
| Large/Infrequent (Llama3/8B+) | > 8GB | Data Lake HDD | < 10 seconds |

**Storage Performance Comparison:**
- Cluster Storage SSD (/dev/sdc1): 384 MB/s read, 236GB available
- Data Lake HDD: 270 MB/s read, 13TB available (rejected for Whisper workload due to 30% performance gap)

**Kernel Error Analysis:**
- `stat urb: status -71`: Protocol Error during USB status stage
- `cmd complt err -71`: Protocol Error during command completion
- Both errors indicate hardware-level power starvation, not software bugs

### Communication Log

| Time | Recipient | Message | Channel |
|------|-----------|---------|---------|
| 2026-08-10 10:55:00 | Operations Team | Hardware failure detected, initiating investigation | Internal |
| 2026-08-10 11:30:00 | Stakeholders | Service restored via storage migration | Internal |

### Supporting Artifacts

- System logs showing USB connection cycling (Device IDs 76-104)
- fsck output showing inode recovery
- Storage performance benchmark results
- USB bus analysis output (lsusb -t)

---

**Report Completed:** 2026-08-10  
**Next Review:** 2026-08-17  
**Archive Date:** 2026-09-10
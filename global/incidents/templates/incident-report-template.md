# Incident Report - [Title]

**Date:** YYYY-MM-DD  
**System/Component:** [Affected System]  
**Severity:** [Critical/High/Medium/Low]  
**Status:** [Active/Resolved/Monitoring]  
**Agent:** [Agent Name/ID]

---

## Executive Summary

[Brief 2-3 sentence summary of the incident, impact, and resolution status]

---

## Problem Statement

**Initial Issue:**
[Description of what was reported or observed]

**Affected Systems:**
- [System 1]
- [System 2]
- [System 3]

**Impact Assessment:**
- **Users Affected:** [Number or description]
- **Duration:** [Start time to end time]
- **Business Impact:** [Description of business impact]
- **Data Impact:** [Any data loss or integrity concerns]

---

## Investigation Findings

### Initial Assessment

**Discovery Method:** [Monitoring report/user report/automated alert]
**First Response Time:** [Time from detection to investigation start]
**Initial Hypothesis:** [Initial theories about root cause]

### Investigation Process

**Steps Taken:**
1. [Investigation step 1]
2. [Investigation step 2]
3. [Investigation step 3]

**Tools Used:**
- [Tool 1 - purpose]
- [Tool 2 - purpose]
- [Tool 3 - purpose]

**Key Findings:**
- [Finding 1]
- [Finding 2]
- [Finding 3]

### Evidence Inventory & Query Audits

| Timestamp (UTC) | Source System / DB | Query Predicate / Command | Row/Event Count | Purpose / Scope |
|---|---|---|---|---|
| YYYY-MM-DD HH:MM | [e.g. SQLite / Postgres] | `SELECT ... WHERE ...` | [Count] | [e.g. Isolate historical failed generation jobs] |
| YYYY-MM-DD HH:MM | [e.g. Container logs] | `kubectl logs ... | grep -i ...` | [Count] | [e.g. Capture rate limiter preemption alerts] |

---

## Root Cause Analysis

### Primary Root Cause

**Description:** [Clear description of the primary root cause]
**Category:** [Configuration/Code/Infrastructure/Process/External]
**Evidence:** [Supporting evidence for root cause conclusion]

### Contributing Factors

1. **Factor 1:** [Description]
2. **Factor 2:** [Description]
3. **Factor 3:** [Description]

### Telemetry Metrics Disambiguation

| Timing / Timer Metric | Handshake / Overhead Component | Payload Execution Component | Target Threshold | Disambiguation Notes |
|---|---|---|---|---|
| [e.g. Preemption Cost Timer] | [e.g. GPUNanny _ensure_awake()] | [e.g. StableDiffusion txt2img API] | [e.g. <3.0s] | [e.g. Ensure payload generation duration is not blended into preemption metrics] |

### Timeline

| Time | Event | Impact |
|------|-------|--------|
| HH:MM | [Event description] | [Impact level] |
| HH:MM | [Event description] | [Impact level] |
| HH:MM | [Event description] | [Impact level] |

---

## Resolution Actions

### Immediate Actions

**Action 1:**
- **Description:** [What was done]
- **Owner:** [Who performed it]
- **Time:** [When it was completed]
- **Result:** [Outcome]

**Action 2:**
- **Description:** [What was done]
- **Owner:** [Who performed it]
- **Time:** [When it was completed]
- **Result:** [Outcome]

### Configuration Changes

**Change 1:**
- **File/Component:** [What was changed]
- **Before:** [Previous state]
- **After:** [New state]
- **Reason:** [Why this change was needed]

**Change 2:**
- **File/Component:** [What was changed]
- **Before:** [Previous state]
- **After:** [New state]
- **Reason:** [Why this change was needed]

### Call-Site Compatibility & Database Purge Governance Checklists

#### 1. Code Signature Change & Call-Site Compatibility Checklist
- [ ] **Exhaustive codebase search** performed (e.g. `grep -rn "function_name"` or `git grep`).
- **Call-Site Inventory:**
  - Call-Site 1: [File Path & Line Number] (e.g. `apps/storyloom-api/app/app.py:5733`)
  - Call-Site 2: [File Path & Line Number] (e.g. `apps/storyloom-api/app/services/avatar_job.py:132`)
- [ ] **Unpacking / Contract Changes** applied to all listed call sites.
- [ ] **Test coverage verification** executed locally to prevent unpack/runtime errors.

#### 2. Database Purge & Table Cleanup Checklist
- [ ] **Purge Date/Status Predicate defined** (no unscoped deletes allowed).
- **Target SQL Predicate:** `DELETE FROM [table] WHERE [predicate]`
- [ ] **Pre-purge count query executed**. Value: `[Pre-purge row count]`
- [ ] **Database snapshot or export completed** before running the delete.
- [ ] **Post-purge count query executed** to confirm expected row drop. Value: `[Post-purge row count]`
- **Rollback / Recover Plan:** [Description of how to restore if unexpected rows are affected]

---

## Validation Results

### Testing Performed

**Test 1:** [Description]
- **Expected Result:** [What should happen]
- **Actual Result:** [What actually happened]
- **Status:** ✅ Pass / ❌ Fail

**Test 2:** [Description]
- **Expected Result:** [What should happen]
- **Actual Result:** [What actually happened]
- **Status:** ✅ Pass / ❌ Fail

### Metrics Comparison

**Before Incident:**
- [Metric 1]: [Value]
- [Metric 2]: [Value]
- [Metric 3]: [Value]

**After Resolution:**
- [Metric 1]: [Value]
- [Metric 2]: [Value]
- [Metric 3]: [Value]

**Improvement:** [Description of improvement]

---

## Follow-up Actions

### Immediate (Next 24-48 Hours)

- [ ] [Action item 1] - [Owner] - [Due date]
- [ ] [Action item 2] - [Owner] - [Due date]
- [ ] [Action item 3] - [Owner] - [Due date]

### Short-term (Next 1-2 Weeks)

- [ ] [Action item 1] - [Owner] - [Due date]
- [ ] [Action item 2] - [Owner] - [Due date]
- [ ] [Action item 3] - [Owner] - [Due date]

### Long-term (Next 1-3 Months)

- [ ] [Action item 1] - [Owner] - [Due date]
- [ ] [Action item 2] - [Owner] - [Due date]
- [ ] [Action item 3] - [Owner] - [Due date]

---

## Lessons Learned

### What Went Well

- [Positive aspect 1]
- [Positive aspect 2]
- [Positive aspect 3]

### What Could Be Improved

- [Improvement area 1]
- [Improvement area 2]
- [Improvement area 3]

### Process Changes Needed

- [Process change 1]
- [Process change 2]
- [Process change 3]

---

## Related Documentation

- **Postmortem:** [Link to postmortem if available]
- **Implementation Checklist:** [Link to implementation checklist]
- **Executive Summary:** [Link to executive summary]
- **Related ADRs:** [Links to related architectural decisions]
- **Previous Incidents:** [Links to related previous incidents]

---

## Appendices

### Technical Details

[Additional technical information, logs, configurations, etc.]

### Communication Log

| Time | Recipient | Message | Channel |
|------|-----------|---------|---------|
| HH:MM | [Team/Stakeholders] | [Message summary] | [Slack/Email/etc] |
| HH:MM | [Team/Stakeholders] | [Message summary] | [Slack/Email/etc] |

### Supporting Artifacts

- [Log file 1] - [Location]
- [Configuration backup] - [Location]
- [Screenshots] - [Location]

---

**Report Completed:** YYYY-MM-DD HH:MM  
**Next Review:** [Date for follow-up review]
**Archive Date:** [Date when this should move to archive]

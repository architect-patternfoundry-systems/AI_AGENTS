# Postmortem - [Incident Title]

**Incident Date:** YYYY-MM-DD  
**Postmortem Date:** YYYY-MM-DD  
**Incident Duration:** [Start time to end time]  
**Severity:** [Critical/High/Medium/Low]  
**Facilitator:** [Name/Agent]  
**Participants:** [List of participants]

---

## Executive Summary

[2-3 paragraph summary of the incident, impact, resolution, and key takeaways]

---

## Timeline

### Incident Timeline

| Time (UTC) | Event | Impact | Detection Method |
|------------|-------|--------|------------------|
| YYYY-MM-DD HH:MM | [Event description] | [Impact level] | [How it was detected] |
| YYYY-MM-DD HH:MM | [Event description] | [Impact level] | [How it was detected] |
| YYYY-MM-DD HH:MM | [Event description] | [Impact level] | [How it was detected] |

### Response Timeline

| Time (UTC) | Action | Owner | Outcome |
|------------|-------|-------|---------|
| YYYY-MM-DD HH:MM | [Response action] | [Who took it] | [Result] |
| YYYY-MM-DD HH:MM | [Response action] | [Who took it] | [Result] |
| YYYY-MM-DD HH:MM | [Response action] | [Who took it] | [Result] |

---

## Impact Assessment

### User Impact

**Affected Users:** [Number or description]
**Geographic Impact:** [Regions affected]
**Service Degradation:** [Description of service impact]
**User-Facing Symptoms:** [What users experienced]

### Business Impact

**Revenue Impact:** [Estimated financial impact if applicable]
**Operational Impact:** [Effect on business operations]
**Customer Impact:** [Effect on customers/partners]
**Reputation Impact:** [Brand or trust implications]

### Technical Impact

**Systems Affected:**
- [System 1] - [Impact level]
- [System 2] - [Impact level]
- [System 3] - [Impact level]

**Data Impact:**
- **Data Loss:** [Yes/No - details]
- **Data Corruption:** [Yes/No - details]
- **Data Recovery:** [Recovery process and outcome]

**Performance Impact:**
- **Latency:** [Before vs After metrics]
- **Throughput:** [Before vs After metrics]
- **Error Rates:** [Before vs After metrics]

---

## Root Cause Analysis

### Primary Root Cause

**Description:** [Detailed description of the primary root cause]
**Category:** [Configuration/Code/Infrastructure/Process/External/Security]
**Subcategory:** [More specific category]

**Root Cause Chain:**
1. [Event 1]
2. [Event 2] - caused by Event 1
3. [Event 3] - caused by Event 2
4. [Incident] - caused by Event 3

### Contributing Factors

**Factor 1:** [Description]
- **Why it existed:** [Underlying reason]
- **How it contributed:** [Connection to incident]

**Factor 2:** [Description]
- **Why it existed:** [Underlying reason]
- **How it contributed:** [Connection to incident]

**Factor 3:** [Description]
- **Why it existed:** [Underlying reason]
- **How it contributed:** [Connection to incident]

### Five Whys Analysis

1. **Why did the incident happen?** [Answer]
2. **Why did that happen?** [Answer]
3. **Why did that happen?** [Answer]
4. **Why did that happen?** [Answer]
5. **Why did that happen?** [Answer - root cause]

---

## Resolution and Recovery

### Immediate Mitigation

**Action 1:** [Description]
- **Time to Implement:** [Duration]
- **Effectiveness:** [Did it work?]
- **Side Effects:** [Any unintended consequences]

**Action 2:** [Description]
- **Time to Implement:** [Duration]
- **Effectiveness:** [Did it work?]
- **Side Effects:** [Any unintended consequences]

### Permanent Fix

**Solution Implemented:** [Description of permanent fix]
- **Implementation Time:** [Duration]
- **Testing Performed:** [Description of testing]
- **Rollback Plan:** [If rollback was needed]

### Validation

**How We Verified the Fix:**
- [Validation method 1]
- [Validation method 2]
- [Validation method 3]

**Current Status:** [Confirmed resolved/Monitoring/Recurring]

---

## Lessons Learned

### What Went Well

**Detection:**
- [What worked well in detecting the incident]
- [Why it worked well]

**Response:**
- [What worked well in the response]
- [Why it worked well]

**Resolution:**
- [What worked well in the resolution]
- [Why it worked well]

**Communication:**
- [What worked well in communication]
- [Why it worked well]

### What Could Be Improved

**Detection:**
- [What could be improved in detection]
- [How to improve it]

**Response:**
- [What could be improved in response]
- [How to improve it]

**Resolution:**
- [What could be improved in resolution]
- [How to improve it]

**Communication:**
- [What could be improved in communication]
- [How to improve it]

### Gaps Identified

**Monitoring Gaps:**
- [Gap 1] - [Impact]
- [Gap 2] - [Impact]

**Process Gaps:**
- [Gap 1] - [Impact]
- [Gap 2] - [Impact]

**Documentation Gaps:**
- [Gap 1] - [Impact]
- [Gap 2] - [Impact]

**Tooling Gaps:**
- [Gap 1] - [Impact]
- [Gap 2] - [Impact]

---

## Action Items

### Preventive Actions

| Priority | Action | Owner | Due Date | Status |
|----------|--------|-------|----------|---------|
| [P1/P2/P3] | [Specific action] | [Owner] | [Date] | [Open/In Progress/Done] |
| [P1/P2/P3] | [Specific action] | [Owner] | [Date] | [Open/In Progress/Done] |
| [P1/P2/P3] | [Specific action] | [Owner] | [Date] | [Open/In Progress/Done] |

### Process Improvements

| Priority | Action | Owner | Due Date | Status |
|----------|--------|-------|----------|---------|
| [P1/P2/P3] | [Specific process change] | [Owner] | [Date] | [Open/In Progress/Done] |
| [P1/P2/P3] | [Specific process change] | [Owner] | [Date] | [Open/In Progress/Done] |
| [P1/P2/P3] | [Specific process change] | [Owner] | [Date] | [Open/In Progress/Done] |

### Documentation Updates

| Priority | Document | Update Needed | Owner | Due Date | Status |
|----------|----------|---------------|-------|----------|---------|
| [P1/P2/P3] | [Document name] | [What needs updating] | [Owner] | [Date] | [Open/In Progress/Done] |
| [P1/P2/P3] | [Document name] | [What needs updating] | [Owner] | [Date] | [Open/In Progress/Done] |

---

## Risk Assessment

### Remaining Risks

**Risk 1:** [Description]
- **Likelihood:** [High/Medium/Low]
- **Impact:** [High/Medium/Low]
- **Mitigation:** [How to address]

**Risk 2:** [Description]
- **Likelihood:** [High/Medium/Low]
- **Impact:** [High/Medium/Low]
- **Mitigation:** [How to address]

### Future Prevention

**Monitoring Improvements:**
- [Improvement 1]
- [Improvement 2]

**Process Changes:**
- [Change 1]
- [Change 2]

**Architecture Changes:**
- [Change 1]
- [Change 2]

---

## Related Documentation

- **Incident Report:** [Link to incident report]
- **Implementation Checklist:** [Link to implementation checklist]
- **Executive Summary:** [Link to executive summary]
- **Related ADRs:** [Links to related architectural decisions]
- **Change Records:** [Links to related change records]

---

## Appendices

### Technical Details

[Additional technical information, logs, configurations, etc.]

### Communication Timeline

| Time | Audience | Message | Channel | Sender |
|------|----------|---------|---------|--------|
| HH:MM | [Who] | [What was communicated] | [How] | [Who sent it] |
| HH:MM | [Who] | [What was communicated] | [How] | [Who sent it] |

### Meeting Notes

**Postmortem Meeting:** [Date/Time]
**Attendees:** [List]
**Key Discussion Points:**
- [Point 1]
- [Point 2]
- [Point 3]

### Supporting Data

- [Metrics data]
- [Screenshots]
- [Log excerpts]
- [Configuration snapshots]

---

**Postmortem Completed:** YYYY-MM-DD  
**Next Review:** [Date for action item review]  
**Owner:** [Person responsible for follow-up]

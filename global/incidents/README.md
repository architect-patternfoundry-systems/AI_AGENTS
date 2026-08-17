# Incident Documentation Governance

System-wide structure for incident reports, postmortems, implementation checklists, and executive summaries as part of continuous documentation expectations for all AI agents.

## Purpose

Establish standardized documentation practices for:
- **Incident Reports**: Technical investigations and resolutions
- **Postmortems**: Root cause analysis and prevention strategies  
- **Implementation Checklists**: Step-by-step deployment procedures
- **Executive Summaries**: High-level overviews for stakeholders

## Structure

```
AI_AGENTS/global/incidents/
├── README.md                    # This file
├── templates/                   # Document templates
│   ├── incident-report-template.md
│   ├── postmortem-template.md
│   ├── implementation-checklist-template.md
│   └── executive-summary-template.md
├── active/                      # Current/ongoing incidents
│   └── YYYY-MM-DD-incident-title/
│       ├── incident-report.md
│       ├── postmortem.md (if completed)
│       ├── implementation-checklist.md
│       └── executive-summary.md
└── archive/                     # Historical incidents
    └── YYYY-MM-DD-incident-title/
        ├── incident-report.md
        ├── postmortem.md
        ├── implementation-checklist.md
        └── executive-summary.md
```

## Documentation Standards

### When to Create Documentation

**Incident Reports:**
- System outages or degradations
- Security incidents
- Data integrity issues
- Performance problems affecting users
- Any investigation requiring technical analysis

**Postmortems:**
- After incident resolution
- For significant incidents (severity medium+)
- When multiple systems or teams are affected
- When process changes are needed

**Implementation Checklists:**
- Network infrastructure changes
- Security policy modifications
- Major configuration updates
- Cross-system deployments
- Changes requiring rollback procedures

**Executive Summaries:**
- All incidents requiring postmortems
- Major system changes
- Strategic initiatives
- Stakeholder communications

### Document Requirements

**All Documents Must Include:**
- Clear title and date
- Author/agent identification
- Impact assessment
- Timeline and resolution status
- Actionable next steps
- Links to related documents

**Quality Standards:**
- Technical accuracy verified
- Root causes identified (not just symptoms)
- Preventive measures defined
- Success criteria established
- Lessons learned documented

### Audit-Grade Claims & Evidence Standards
All reports must adhere to objective compliance and audit-ready phrasing rules:
- **FACT vs. ASSUMPTION**: Never make speculative statements without explicit data queries. Distinguish observed metrics from hypotheses.
- **NEUTRAL, AUDIT-FRIENDLY TONE**: Use "Validated against the current persisted job records" instead of subjective claims like "empirically proved." Use "Implemented and verified in the current environment" instead of "successfully implemented."
- **EVIDENCE INVENTORY**: All investigation files, snapshots, logs, and database queries must be logged in a dedicated findings table.

### Call-Site Compatibility Audits
When changing a shared utility's signature or type return format (e.g., returning a tuple instead of a scalar):
- **EXHAUSTIVE SEARCH**: You must run an exhaustive codebase scan (e.g. `grep -rn` or `git grep`) to locate every reference call site.
- **INVENTORY AND UNPACKING**: Create a call-site inventory list in the implementation checklist or template. Change all call sites in the same deployment step.
- **TEST VERIFICATION**: Run local test suites covering the change boundaries to prevent silent unpacking/binding runtime failures.

### Database Purge & Cleanup Governance
When resolving data degradation issues through table or index cleanup:
- **SCOPE RESTRICTION**: Never execute unscoped database purges. All purges must use explicit WHERE filters targeting only the historical failed state.
- **PRE & POST AUDITS**: Responders must execute pre-purge row-count validation, capture a database snapshot/export where applicable, run the targeted delete query, and record post-purge row-count validation in the report.

### Telemetry & Health Check Disambiguation
To prevent metrics regression and false-positive alert trashing:
- **OVERHEAD VS. PAYLOAD**: Telemetry tracking system overhead, provisioning cost, or preemption duration must only measure the isolated handshake/warm-up phase. Never wrap the actual execution payload (e.g. inference runtime, heavy job processing) inside the overhead timer.
- **SIGNAL PRESERVATION**: Verify that metrics continue to function without warnings being triggered by normal operational duration, keeping alarms active exclusively for actual hardware/software stalls.

## Agent Expectations

### Continuous Documentation Requirement

All AI agents **must** create appropriate documentation when:

1. **Investigating Issues:** Create incident report for any technical investigation
2. **Resolving Problems:** Document resolution steps and validation
3. **Making Changes:** Create implementation checklists for system modifications
4. **Completing Work:** Provide executive summary for significant tasks

### Documentation Workflow

```python
def agent_documentation_workflow(task_type: str, complexity: str) -> list:
    """
    Determine required documentation based on task type and complexity
    """
    docs = []
    
    # All investigations get incident reports
    if task_type == "investigation":
        docs.append("incident-report")
        
    # Complex tasks get implementation checklists
    if complexity in ["medium", "high"]:
        docs.append("implementation-checklist")
        
    # Significant work gets executive summaries
    if complexity == "high" or task_type in ["outage", "security"]:
        docs.append("executive-summary")
        
    # Resolved incidents get postmortems
    if task_type == "incident" and complexity == "high":
        docs.append("postmortem")
        
    return docs
```

### File Naming Convention

```
active/YYYY-MM-DD-[system]-[brief-description]/
├── incident-report.md
├── postmortem.md 
├── implementation-checklist.md
└── executive-summary.md
```

Examples:
- `active/2026-07-21-prometheus-grafana-scrape-failures/`
- `active/2026-07-15-authentication-service-outage/`
- `active/2026-07-10-database-migration-blocking/`

## Templates

### Incident Report Template

See `templates/incident-report-template.md` for standard structure.

Required sections:
- Executive Summary
- Problem Statement
- Investigation Findings
- Root Cause Analysis
- Resolution Actions
- Validation Results
- Follow-up Actions

### Postmortem Template

See `templates/postmortem-template.md` for standard structure.

Required sections:
- Timeline
- Impact Assessment
- Root Cause Analysis
- Resolution and Recovery
- Lessons Learned
- Action Items

### Implementation Checklist Template

See `templates/implementation-checklist-template.md` for standard structure.

Required sections:
- Pre-deployment Requirements
- Implementation Steps
- Validation Procedures
- Rollback Procedures
- Success Criteria

### Executive Summary Template

See `templates/executive-summary-template.md` for standard structure.

Required sections:
- Quick Impact
- Root Cause
- What Was Fixed
- Remaining Issues
- Next Steps

## Lifecycle Management

### Active → Archive Transition

Move incidents from `active/` to `archive/` when:
- All resolution actions are complete
- Implementation checklists are executed
- Postmortem is completed (if required)
- Executive summary is created
- 30 days have passed since resolution

### Retention Policy

- **Active incidents:** Keep in `active/` for 30 days post-resolution
- **Archive incidents:** Keep indefinitely for historical reference
- **Templates:** Update quarterly based on feedback
- **This governance:** Review annually for effectiveness

## Integration with AI_AGENTS

### Loading Rules

Agents should load incident documentation standards as part of global governance:

```python
def load_governance_rules():
    rules = {}
    
    # Load standard global governance
    rules.update(load_from_path("AI_AGENTS/global/"))
    
    # Load incident documentation standards
    rules.update(load_from_path("AI_AGENTS/global/incidents/"))
    
    return rules
```

### Agent Behavior

When an agent completes a task that requires documentation:

1. **Assess documentation requirements** based on task type and complexity
2. **Create appropriate documents** using standard templates
3. **Store in correct location** (active/ or archive/)
4. **Reference in task completion** with file paths
5. **Update task tracking** with documentation status

## Quality Assurance

### Review Process

- **Self-review:** Agents validate technical accuracy before completion
- **Template compliance:** Ensure all required sections are complete
- **Cross-reference:** Link to related incidents and ADRs
- **Actionability:** Verify all next steps are specific and achievable

### Continuous Improvement

- **Template refinement:** Update based on agent feedback
- **Process optimization:** Streamline documentation workflow
- **Effectiveness measurement:** Track documentation usage and value
- **Training:** Update agent capabilities based on lessons learned

## Examples

### Example Incident

**Prometheus/Grafana Health Check (2026-07-21)**
- Location: `active/2026-07-21-prometheus-grafana-scrape-failures/`
- Documents: incident-report.md, implementation-checklist.md, executive-summary.md
- Status: Resolved, awaiting archive transition

### Reference Implementation

See the current Prometheus/Grafana investigation as a reference:
- `/tmp/prometheus-grafana-health-check-incident-report.md`
- `/tmp/gitops-implementation-checklist.md`  
- `/tmp/prometheus-grafana-health-check-executive-summary.md`

## Contributing

- **Template changes:** Require governance review
- **Process updates:** Document rationale and get consensus
- **New document types:** Follow template creation process
- **Standard modifications:** Update this README with changes

## Related Governance

- **AI_AGENTS/global/operations.md** - Operational standards
- **AI_AGENTS/global/adr/** - Architectural decisions
- **AI_AGENTS/context/** - Context-specific overrides

---

**Last Updated:** 2026-07-21  
**Governance Owner:** AI Agents System  
**Review Cycle:** Quarterly

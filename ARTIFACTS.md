# AI_AGENTS Artifacts Index

This file indexes all major architectural proposals, design specifications, security runbooks, checklists, and incident reports in the AI_AGENTS governance system.

## Artifact Registration

Artifacts are classified using the following taxonomy:
- `[PROPOSAL]` - Architectural proposals and design documents
- `[SPEC]` - Technical specifications and implementation details
- `[RUNBOOK]` - Operational procedures and response playbooks
- `[CHECKLIST]` - Implementation and validation checklists
- `[REPORT]` - Incident reports and investigation findings

## Incident Reports

### Active Incidents

- `[REPORT]` **2026-08-10: Power Starvation and Connection Cycling of G-Technology ArmorLock SSD**
  - Location: `global/incidents/active/2026-08-10-g-technology-armorlock-ssd-failure/`
  - Files:
    - `incident-report.md` - Comprehensive analysis of USB protocol fallback, power starvation, and connection cycling
  - Status: Resolved
  - Severity: Critical
  - Last Updated: 2026-08-10 16:00 UTC
  - Resolution: Storage migrated to Cluster Storage SSD, SLO-based storage policy implemented, USB cabling standards updated

- `[REPORT]` **2026-08-10: Disk Space Cleanup and Zombie Pod Analysis**
  - Location: `global/incidents/active/2026-08-10-disk-space-cleanup-and-zombie-pod-analysis/`
  - Files:
    - `incident-report.md` - Disk space cleanup analysis and zombie pod pattern investigation
    - `image-rebuild-plan.md` - Systematic plan to rebuild missing container images and fix dependencies
    - `failing-pods-inventory.md` - Authoritative inventory of 21 failing pods with node-level registry validation
    - `registry-migration-inventory.yaml` - Complete workload inventory with migration plan, validation rules, and audit trail
  - Status: Resolved (disk space), IN PROGRESS (registry migration - canary successful, 48 workloads pending)
  - Severity: High
  - Last Updated: 2026-08-10 22:00 UTC
  - Resolution: 92GB disk space reclaimed (89% → 79%), IN PROGRESS: Canary deployment successful (gacs/k8s-state-ingestor), 48 workloads pending migration (45 deployments + 3 daemonsets, 55 image references), 49 total discovered affected workloads, ADR-016 approved (Option A: deliberate split transport), Batch 1 planned but not authorized (per-workload artifact evidence required)

- `[REPORT]` **2026-08-07: Disk Space Crisis and k3s Eviction Failure**
  - Location: `global/incidents/active/2026-08-07-disk-space-crisis-k3s-eviction-failure/`
  - Files:
    - `incident-report.md` - Comprehensive technical investigation and root cause analysis (final corrected version)
    - `incident-report-old.md` - Previous version with obsolete sections (preserved for reference)
    - `incident-report-user-edited.md` - User-edited version with partial corrections (preserved for reference)
    - `executive-summary.md` - High-level overview for stakeholders
    - `implementation-checklist.md` - Step-by-step remediation procedures
  - Status: Remediated Pending Verification
  - Severity: Critical
  - Last Updated: 2026-08-07 16:35 UTC
  - Database ID: 23cd8cdf-f41a-4c58-b630-253e06574b77 (devops-platform)
  - Resolution: 122.4 GiB disk space freed, eviction manager resolved on cortex node, registry healthy, MinIO recovered, pgbouncer image reference invalid, Grafana eviction loop active

### Archived Incidents

- `[REPORT]` **2026-07-21: Prometheus Grafana Scrape Failures**
  - Location: `global/incidents/active/2026-07-21-prometheus-grafana-scrape-failures/`
  - Status: Resolved
  - Severity: High

- `[REPORT]` **2026-07-22: Avatar Pipeline Timeouts and Serving Leaks**
  - Location: `global/incidents/active/2026-07-22-avatar-pipeline-timeouts-and-serving-leaks/`
  - Status: Resolved
  - Severity: High

- `[REPORT]` **2026-07-22: Grafana Datasource Fetch Failures**
  - Location: `global/incidents/active/2026-07-22-grafana-datasource-fetch-failures/`
  - Status: Resolved
  - Severity: High

- `[REPORT]` **2026-07-22: Neo4j Relationship Self Loops**
  - Location: `global/incidents/active/2026-07-22-neo4j-relationship-self-loops/`
  - Status: Resolved
  - Severity: Medium

- `[REPORT]` **2026-07-22: Tilt Hot Reload Loops**
  - Location: `global/incidents/active/2026-07-22-tilt-hot-reload-loops/`
  - Status: Resolved
  - Severity: Medium

- `[REPORT]` **2026-08-02: CTS Transcription Queue Recovery**
  - Location: `global/incidents/active/2026-08-02-cts-transcription-queue-recovery/`
  - Status: Resolved
  - Severity: High

## Architectural Decisions (ADRs)

### Global ADRs

- `[PROPOSAL]` **ADR-013: Drop-Folder Worker**
  - Location: `global/adr/ADR-013-drop-folder-worker.md`
  - Focus: ToneRoot drop-folder architecture

- `[PROPOSAL]` **ADR-014: Ingestion Gateway**
  - Location: `global/adr/ADR-014-ingestion-gateway.md`
  - Focus: Gateway contract and security

- `[PROPOSAL]` **ADR-015: Resource Resolution Priority Framework**
  - Location: `global/adr/ADR-015-resource-resolution-priority.md`
  - Focus: Config, plugin, asset resolution patterns

## Operational Standards

- `[SPEC]` **Infrastructure Standards**
  - Location: `global/infrastructure.md`
  - Focus: NFS paths, connectivity, ToneRoot layout

- `[SPEC]` **Operations Standards**
  - Location: `global/operations.md`
  - Focus: Monitoring, logging, alerting, incident management

- `[SPEC]` **Security Standards**
  - Location: `global/security.md`
  - Focus: Secret management, network security, compliance

## Domain-Specific Rules

- `[SPEC]` **Next.js Rules**
  - Location: `domains/nextjs/rules.md`
  - Focus: React/Next.js patterns

- `[SPEC]` **Kubebuilder Rules**
  - Location: `domains/kubernetes/kubebuilder.md`
  - Focus: Kubernetes operator development

- `[SPEC]` **Python Rules**
  - Location: `domains/python/rules.md`
  - Focus: Python development patterns

- `[SPEC]` **Flux Rules**
  - Location: `domains/infrastructure/flux.md`
  - Focus: GitOps and infrastructure as code

## Templates

- `[CHECKLIST]` **Incident Report Template**
  - Location: `global/incidents/templates/incident-report-template.md`

- `[CHECKLIST]` **Postmortem Template**
  - Location: `global/incidents/templates/postmortem-template.md`

- `[CHECKLIST]` **Implementation Checklist Template**
  - Location: `global/incidents/templates/implementation-checklist-template.md`

- `[CHECKLIST]` **Executive Summary Template**
  - Location: `global/incidents/templates/executive-summary-template.md`

## Artifact Mirroring

Per the AI_AGENTS governance operations standards, major artifacts are mirrored to `docs/artifacts/` for cross-agent knowledge retrieval via MCP.

### Mirrored Artifacts

- `[REPORT]` **2026-08-10: Power Starvation and Connection Cycling of G-Technology ArmorLock SSD**
  - Mirror Location: `docs/artifacts/2026-08-10-g-technology-armorlock-ssd-failure-incident-report.md`
  - Original: `global/incidents/active/2026-08-10-g-technology-armorlock-ssd-failure/incident-report.md`

- `[REPORT]` **2026-08-10: Disk Space Cleanup and Zombie Pod Analysis**
  - Mirror Location: `docs/artifacts/2026-08-10-disk-space-cleanup-and-zombie-pod-analysis-incident-report.md`
  - Original: `global/incidents/active/2026-08-10-disk-space-cleanup-and-zombie-pod-analysis/incident-report.md`

- `[REPORT]` **2026-08-07: Disk Space Crisis and k3s Eviction Failure**
  - Mirror Location: `docs/artifacts/2026-08-07-disk-space-crisis-k3s-eviction-failure-incident-report.md`
  - Original: `global/incidents/active/2026-08-07-disk-space-crisis-k3s-eviction-failure/incident-report.md`

- `[REPORT]` **2026-08-07: Disk Space Crisis Executive Summary**
  - Mirror Location: `docs/artifacts/2026-08-07-disk-space-crisis-k3s-eviction-failure-executive-summary.md`
  - Original: `global/incidents/active/2026-08-07-disk-space-crisis-k3s-eviction-failure/executive-summary.md`

- `[CHECKLIST]` **2026-08-07: Disk Space Crisis Implementation Checklist**
  - Mirror Location: `docs/artifacts/2026-08-07-disk-space-crisis-k3s-eviction-failure-implementation-checklist.md`
  - Original: `global/incidents/active/2026-08-07-disk-space-crisis-k3s-eviction-failure/implementation-checklist.md`

## Access and Discovery

### MCP Integration
Artifacts indexed in this file are automatically discoverable via the `homelab-mcp` server (when available) using the `get_walkthrough` tool.

### Fallback Access
When MCP is unavailable, artifacts can be accessed directly from their documented locations in this index.

## Contribution Guidelines

When adding new artifacts:
1. Classify using the appropriate taxonomy tag
2. Create the artifact in the appropriate directory
3. Add an entry to this ARTIFACTS.md file
4. Mirror major artifacts to `docs/artifacts/`
5. Verify MCP discoverability (when available)

---

**Last Updated:** 2026-08-10 16:15 UTC  
**Governance Version:** Phase 1 (Active)  
**MCP Status:** Configured with BRAIN_DIR=/home/cortex/workspace
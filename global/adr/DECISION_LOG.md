# ADR Decision Log

This document tracks all Architectural Decision Records (ADRs) in the AI_AGENTS governance system.

## Decision Log Table

| ADR ID | Title | Status | Date | Author | Category |
|--------|-------|--------|------|--------|----------|
| ADR-013 | Drop-Folder Worker | Accepted | 2025-XX-XX | Governance Team | Architecture |
| ADR-014 | Ingestion Gateway | Accepted | 2025-XX-XX | Governance Team | Architecture |
| ADR-015 | Resource Resolution Priority Framework | Accepted (Enhanced) | 2025-XX-XX | Governance Team | Architecture |
| ADR-016 | Batch Generation Concurrency | Accepted | 2025-XX-XX | Governance Team | Operations |
| ADR-017 | Sovereign Media Intake | Accepted | 2025-XX-XX | Governance Team | Architecture |
| ADR-018 | KEDA Flux Tilt Arbitration | Accepted | 2025-XX-XX | Governance Team | Infrastructure |
| ADR-019 | Neo4j Dual Scheme Routing | Accepted | 2025-XX-XX | Governance Team | Architecture |
| ADR-020 | GPU Nanny Arbitration | Accepted | 2025-XX-XX | Governance Team | Operations |
| ADR-021 | Avatar Staged Commit | Accepted | 2025-XX-XX | Governance Team | Operations |
| ADR-022 | SMB First Auth Strategy | Accepted | 2025-XX-XX | Governance Team | Security |
| ADR-023 | Celery Schedule Configuration | Accepted | 2025-XX-XX | Governance Team | Operations |
| ADR-024 | Cloudflare Tunnel Public Edge Pattern | Accepted | 2025-XX-XX | Governance Team | Infrastructure |
| ADR-025 | Admin Auth Strategy | Accepted | 2025-XX-XX | Governance Team | Security |
| ADR-026 | Unified Log Intelligence Platform | Accepted | 2026-07-19 | Platform Team | Observability |
| ADR-027 | Standardize ToneRoot Logging | Accepted | 2026-08-01 | Platform Team | Observability |
| ADR-028 | Service Delivery and Break-Glass Recovery Framework | Accepted (Certified) | 2026-08-16 | Platform Team | Infrastructure |
| ADR-029 | Continuous DR Runbook Graph and Automated Recertification | Accepted | 2026-08-17 | Platform Team | Operations |
| ADR-030 | Model Caches Use Static Local PVs on cortex | Accepted (file pending merge on branch `feature/adr-030-static-local-pvs`) | 2026-08-19 | Platform Team | Infrastructure |
| ADR-031 | Change Impact Analysis & Stakeholder Governance | Accepted | 2026-08-20 | Platform Team | Governance |
| ADR-032 | Federated Governance & Multi-Plane Evidence Architecture | Accepted | 2026-08-22 | Platform Team | Governance |
| ADR-033 | ML Model Storage Patterns | Accepted | 2026-08-25 | Platform Team | Infrastructure |
| ADR-034 | ML Model Storage Vulnerability FMEA | Accepted | 2026-08-26 | Platform Team | Security |
| ADR-035 | CTS Temporal Pilot — Ollama Lease Wiring | Accepted (Implementation Gated) | 2026-09-04 | Platform Team | Architecture |
| ADR-036 | Temporal Integration Standard — Cross-App Durable Orchestration | Accepted | 2026-09-05 | Platform Team | Architecture |
| ADR-037 | Credential Rotation Lifecycle Workflow | Proposed | 2026-09-05 | Platform Team | Security |
| ADR-038 | Credential Discovery, Inventory, and Enrollment Standard | Proposed | 2026-09-05 | Platform Team | Security |
| ADR-039 | Canonical CMDB and Authority Consolidation | Accepted (pending merge; branch `adr/039-observation-plane`, mirrored to aegis-control-plane) | 2026-09-23 | Platform Team | Governance |
| ADR-040 | Candidate Matching and Curation | Accepted (mirrored to aegis-control-plane @ AI_AGENTS@78d52d9) | 2026-09-24 | Platform Team | Governance |
| ADR-041 | GPU Tenancy Model — Registry, Classes, and Onboarding | Accepted (hosted in `infrastructure` repo: `docs/artifacts/proposals/ADR-041-gpu-tenancy-model.md`) | 2026-09-24 | Platform Team | Infrastructure |
| ADR-042 | Canonical Linkage Materialization Semantics | Earmarked — pending renumber of branch `adr/041-linkage-materialization` (dual-claimed 041; first-merged wins per ADR_NUMBERING.md) | 2026-09-24 | Platform Team | Governance |

> **Next free: ADR-043.** Numbers are allocated only by a merged row in this
> table — see `ADR_NUMBERING.md` for the full allocation policy, tiebreak rules,
> and repo-local series (`INFRA-ADR-*`) guidance.

## Legacy duplicate numbers (grandfathered, do not rename files)

The following files share a number on `main`. The first-listed is the canonical
entry above; suffix rows exist for cross-reference disambiguation only.

| Suffix | File | Note |
|--------|------|------|
| ADR-015-b | `ADR-015-ollama-model-consolidation.md` | duplicate of 015 |
| ADR-016-a … ADR-016-g | `ADR-016-{batch-generation-concurrency, enforce-subpath-mounts, gacs-data-retention, persistent-storage, registry-transport-split, scale-to-zero-transcription, split-dns-routing}.md` | seven files share 016 |
| ADR-023-b | `ADR-023-cloudflare-tunnel-public-edge-pattern.md` | duplicate of 023 |
| ADR-026-b | `ADR-026-gpu-scheduler-policy-baseline.md` | duplicate of 026 |
| ADR-035-b | `ADR-035-dependency-git-status.md` | duplicate of 035 |

## Categories

- **Architecture:** System architecture and design decisions
- **Operations:** Operational procedures, DR, and automation
- **Infrastructure:** Infrastructure, GitOps, and deployment decisions
- **Security:** Security and access control decisions
- **Observability:** Monitoring, logging, and alerting decisions

## Status Definitions

- **Proposed:** ADR is proposed for committee review
- **Accepted:** ADR has been accepted and implemented
- **Rejected:** ADR has been rejected
- **Deprecated:** ADR has been deprecated by a newer ADR
- **Superseded:** ADR has been superseded by a newer ADR

## Review Process

1. **Proposal:** ADR is proposed with status "Proposed"
2. **Review:** Committee reviews the ADR
3. **Decision:** Committee accepts, rejects, or requests changes
4. **Implementation:** Accepted ADRs are implemented
5. **Tracking:** Decision log is updated with final status

## Document Control

**Version:** 1.4
**Last Updated:** September 24, 2026
**Next Review:** Monthly
**Maintained By:** AI_AGENTS Governance Team
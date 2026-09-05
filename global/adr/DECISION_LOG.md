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
| ADR-030 | Model Caches Use Static Local PVs on cortex | Accepted (Implemented) | 2026-08-19 | Platform Team | Infrastructure |
| ADR-031 | Change Impact Analysis & Stakeholder Governance | Accepted | 2026-08-20 | Platform Team | Governance |
| ADR-032 | Federated Governance & Multi-Plane Evidence Architecture | Accepted | 2026-08-22 | Platform Team | Governance |
| ADR-033 | ML Model Storage Patterns | Accepted | 2026-08-25 | Platform Team | Infrastructure |
| ADR-034 | ML Model Storage Vulnerability FMEA | Accepted | 2026-08-26 | Platform Team | Security |
| ADR-035 | CTS Temporal Pilot — Ollama Lease Wiring | Accepted (Implementation Gated) | 2026-09-04 | Platform Team | Architecture |
| ADR-036 | Temporal Integration Standard — Cross-App Durable Orchestration | Accepted | 2026-09-05 | Platform Team | Architecture |

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

**Version:** 1.3
**Last Updated:** September 5, 2026
**Next Review:** Monthly
**Maintained By:** AI_AGENTS Governance Team
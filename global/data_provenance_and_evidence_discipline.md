# Global Governance: Data Provenance & Epistemic Evidence Discipline
**Standard:** NIST SP 800-53 CM-3, AC-3, SC-28, SC-13, AU-9, MP-6, IA-7, SA-11  
**Scope:** Universal across all AI Agents (`antigravity-cli`, `devin`, `claude-code`, subagent swarms)

---

## 🔬 1. Epistemic Evidence Discipline Invariant

1. **Observed Facts vs. Inferred Mechanism**:
   - Explicitly separate primary observations from inferred mechanisms.
   - Use precise, evidence-bounded phrasing: *"Target health is consistent with reuse of pre-existing TCP/HTTP/2 sessions"* rather than asserting session reuse is conclusively proven without socket-level tracing.
   - Avoid subjective or emotionally charged language (e.g. replace "contaminated" with *"Target status may reflect pre-existing connections; it is not a valid durable-access acceptance signal until fresh connections are tested."*).

2. **Clean-State / Fresh-Connection Verification**:
   - Do not rely on persistent TCP sessions (which persist up to 86,400s under Linux conntrack) to validate network policies or access rules.
   - Force a controlled fresh connection (e.g. Pod restart or session termination) before declaring an ingress/egress policy verified.

---

## 📚 2. The 4-Quadrant Engineering Package Standard

All major technical proposals and incident remediations must provide 4 unified functional views:
* **[REPORT]**: Investigation findings, bounded facts, telemetry analysis.
* **[PROPOSAL]**: Declarative GitOps manifests, architectural design, CSDM service mapping.
* **[RUNBOOK]**: Step-by-step implementation procedures with automated/manual rollback commands.
* **[CHECKLIST]**: Pre-reconciliation gates, fresh-connection tests, and Definition of Done.

---

## 🚦 3. Single-Path Staged GitOps Remediation (A1–A5)

* **Render Pipeline Validation**: Validate manifests with `kustomize build` / `helm template` before staging.
* **Ownership Verification**: Reconcile source repositories and eliminate duplicate monitors/resources.
* **Path-by-Path Execution**: Apply and verify one path at a time.
* **Fresh Connection Acceptance**: Restart consumer/scraper to verify new handshakes succeed.
* **Rollback Readiness**: Retain verified rollback commit prior to each step.

---

## 📦 4. Data Provenance & Artifact Registration Protocol

* **Fixed Taxonomy**: Assign fixed tags: `[PROPOSAL]`, `[SPEC]`, `[RUNBOOK]`, `[CHECKLIST]`, `[REPORT]`.
* **Mirroring**: Save file to `docs/artifacts/<filename>.md` and duplicate in the agent session brain.
* **Index**: Register in root `ARTIFACTS.md` with commit hash and SHA-256 digest.
* **Discoverability**: Ensure retrieval via `homelab-mcp` (`get_walkthrough`).

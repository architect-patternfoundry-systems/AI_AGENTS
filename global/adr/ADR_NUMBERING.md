# ADR Numbering Policy

This policy defines how Architectural Decision Record numbers are allocated across
the PatternFoundry workspace estate. It exists because ADR-041 was dual-claimed in
September 2026 (AI_AGENTS branch `adr/041-linkage-materialization` vs.
`infrastructure` repo GPU tenancy ADR, merged first), and because `global/adr/`
already contains duplicate numbers minted before a canonical ledger was enforced.

## Authority

Per workspace `AGENTS.md`, the **AI_AGENTS repository is the ADR authority for the
estate**. `global/adr/DECISION_LOG.md` is the canonical allocation ledger for the
global sequence. A number is allocated **only** by a merged row in
`DECISION_LOG.md`. Branch names, WIP titles, and filenames in other repos do not
constitute a reservation.

## Rules

1. **One global sequence.** Governance and cross-cutting ADRs are numbered from a
   single estate-wide sequence regardless of which repository hosts the document.

2. **Reserve in the same PR.** An ADR PR must include its `DECISION_LOG.md` row
   (status `Proposed`) in the same change. The number claimed is the lowest
   unallocated number per the ledger's `Next free` marker.

3. **First-merged wins.** If two changes claim the same number, the one merged
   first keeps it. The loser renumbers to the next free number before merge.
   Reviewers should check the ledger, not just the local `global/adr/` directory —
   claims may be pending on branches or live in other repos.

4. **Mirrors cite, don't mint.** Other repositories may mirror an ADR file for
   locality (e.g. `aegis-control-plane/docs/adr/`) but must carry a mirror notice
   naming the canonical number and source-of-truth path. Mirrors do not consume
   numbers.

5. **Repo-local series for implementation-scoped artifacts.** Decisions scoped to a
   single repository's internals may use a prefixed local series (e.g.
   `INFRA-ADR-###` under `infrastructure/docs/artifacts/proposals/`) instead of
   consuming a global number. Promotion to a global number is allowed when the
   decision becomes cross-cutting; the DECISION_LOG records the mapping.

6. **Legacy duplicates are grandfathered.** Files already minted under a duplicate
   number are NOT renamed (cross-references and git history must not break). The
   DECISION_LOG disambiguates them with letter suffixes (`ADR-016-a` … `ADR-016-g`).

## Known collisions and resolutions

| Number | Claims | Resolution |
|--------|--------|------------|
| ADR-041 | `adr/041-linkage-materialization` branch (committed 2026-09-23, unmerged); GPU Tenancy Model (infrastructure repo, merged 2026-09-24) | GPU Tenancy keeps ADR-041 (first-merged wins). `adr/041-linkage-materialization` renumbers to **ADR-042** on rebase; 042 is earmarked for it below. |
| ADR-015/016/023/026/035 | Multiple files per number on `main` | Grandfathered; disambiguated in DECISION_LOG with letter suffixes. |

## Current state

- `global/adr/` on `main`: files through ADR-038 (with legacy duplicates).
- Allocated beyond main: 039 (CMDB/authority consolidation), 040 (candidate
  matching/curation), 041 (GPU tenancy, infrastructure repo).
- Earmarked: 042 (linkage materialization, pending branch renumber).
- **Next free: ADR-043.**

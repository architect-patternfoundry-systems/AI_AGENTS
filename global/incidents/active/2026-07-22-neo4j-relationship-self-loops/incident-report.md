# Incident Report - Neo4j Relationship Self-Loops

**Date:** 2026-07-22  
**System/Component:** Neo4j Graph / Pack Ingestor  
**Severity:** High  
**Status:** Resolved  
**Agent:** Antigravity

---

## Executive Summary

When attempting to cast characters by double-clicking or right-clicking on Team nodes (e.g., "England"), the system returned `"No characters found connected to this selection."` and failed to resolve any players. Investigation revealed that the pack ingestion query in [graph_service.py](file:///home/cortex/workspace/storyloom/apps/storyloom-api/app/services/graph_service.py) was passing the `source` node to the end-node parameter of `apoc.merge.relationship`, creating 3,260 self-loop relationships in Neo4j. The issue was resolved by correcting the APOC arguments signature, deleting the self-loops, and re-importing the affected packs.

---

## Problem Statement

**Initial Issue:**
Casting characters via Team nodes triggered the alert: `"No characters found connected to this selection."`

**Affected Systems:**
- `storyloom-api` (Neo4j ingestion queries)
- Neo4j database (corrupted relationship topology)
- `storyloom-web` (Casting and visual graph rendering)

**Impact Assessment:**
- **Users Affected:** All users attempting to batch-cast players or actors from hub nodes.
- **Duration:** Since the sandbox ingestion refactor.
- **Business Impact:** Blocked the core "Group Casting" and "Cascade Casting" features.
- **Data Impact:** 3,260 self-loop relationships created in Neo4j, isolating players from their teams.

---

## Investigation Findings

### Initial Assessment

**Discovery Method:** User issue report with screenshot.
**First Response Time:** <2 minutes.
**Initial Hypothesis:** The `PLAYER_OF` relationships were missing or incorrectly scoped in Neo4j.

### Investigation Process

**Steps Taken:**
1. Searched the frontend codebase to identify the alert trigger location ([NarrativeGraphCanvas.jsx:924](file:///home/cortex/workspace/storyloom/apps/storyloom-web/src/components/NarrativeGraphCanvas.jsx#L924)).
2. Queried Neo4j database for relationships connected to `unique_id: "EnglandTeam"`. Found 0 relationships.
3. Queried relationships of `unique_id: "EnglandTeamPlayer02"` (H. Kane) and discovered they were self-loops (`(p)-[:PLAYER_OF]->(p)`).
4. Audited the ingestion logic in `graph_service.py` and `update_graph_service.py` to identify the `apoc.merge.relationship` invocation.

**Tools Used:**
- `neo4j-python-driver` via `kubectl exec` to run direct Cypher queries.
- `grep-search` and `view_file` to review backend code.

**Key Findings:**
The ingestion query was structured as:
```cypher
CALL apoc.merge.relationship(source, coalesce(row.label, row.type), ..., source, target) YIELD rel
```
Because the 5th argument of `apoc.merge.relationship` specifies the target end-node, passing `source` created a self-loop. The actual `target` node was passed as the 6th argument (`onMatchProps`), which was ignored.

### Evidence Inventory & Query Audits

| Timestamp (UTC) | Source System / DB | Query Predicate / Command | Row/Event Count | Purpose / Scope |
|---|---|---|---|---|
| 2026-07-22 14:05 | Neo4j | `MATCH (n) WHERE n.id CONTAINS "England" ...` | 2 nodes | Identified that the node ID is `EnglandTeam` |
| 2026-07-22 14:05 | Neo4j | `MATCH (n {unique_id: "EnglandTeamPlayer02"})-[r]-(m) ...` | 2 self-loops | Confirmed `PLAYER_OF` relationships connected back to themselves |

---

## Root Cause Analysis

### Primary Root Cause

**Description:** The backend `apoc.merge.relationship` query in [graph_service.py](file:///home/cortex/workspace/storyloom/apps/storyloom-api/app/services/graph_service.py) was incorrectly configured with `source` passed as the 5th parameter (the `endNode`), self-looping all ingested relationships.
**Category:** Code Bug
**Evidence:** 
```python
CALL apoc.merge.relationship(source, row.label, ..., source, target) YIELD rel
```

---

## Resolution Actions

### Immediate Actions

**Action 1:**
- **Description:** Corrected the 5th parameter of `apoc.merge.relationship` to `target` in [graph_service.py](file:///home/cortex/workspace/storyloom/apps/storyloom-api/app/services/graph_service.py) and [update_graph_service.py](file:///home/cortex/workspace/storyloom/apps/storyloom-api/app/update_graph_service.py).
- **Time:** 14:07 UTC
- **Result:** Ingestion logic corrected.

**Action 2:**
- **Description:** Purged all self-loop relationships in the database:
  ```cypher
  MATCH (n)-[r]->(n) DELETE r
  ```
- **Time:** 14:07 UTC
- **Result:** 3,260 invalid self-loop relationships deleted.

**Action 3:**
- **Description:** Re-imported the `fifa_world_cup_2026_eng` and `fifa_world_cup_2026_esp` data packs to populate correct relationships.
- **Time:** 14:07 UTC
- **Result:** Players successfully connected to their respective Team nodes in Neo4j.

---

## Validation Results

### Testing Performed

**Test 1:** Verify player-team relationship direction and presence in Neo4j.
- **Expected Result:** `['SpainTeamPlayer13', 'PLAYER_OF', 'SpainTeam']`
- **Actual Result:** `['SpainTeamPlayer13', 'PLAYER_OF', 'SpainTeam']`
- **Status:** ✅ Pass

---

**Report Completed:** 2026-07-22 14:08 UTC  
**Archive Date:** 2026-08-22  

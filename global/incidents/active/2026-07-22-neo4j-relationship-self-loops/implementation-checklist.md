# Implementation Checklist - Neo4j Self-Loops Fix

**Created:** 2026-07-22  
**Target Deployment:** 2026-07-22  
**System/Component:** Neo4j Ingestion Queries  
**Change Type:** Code / Database  
**Risk Level:** Medium (Alters DB relationships)  
**Agent:** Antigravity

---

## Overview

**Purpose:** Fix the `apoc.merge.relationship` argument order to prevent self-loop relationships and restore correct player-to-team (and actor-to-movie) graph connections.  
**Scope:** `graph_service.py` and `update_graph_service.py` inside `storyloom-api`.  
**Success Criteria:** Neo4j `PLAYER_OF` relationships connect Player nodes to Team nodes instead of self-looping.

---

## Implementation Steps

### Phase 1: Code Fix

- [x] **Step 1.1:** Perform exhaustive codebase search for `apoc.merge.relationship`.
  - **Call-Site Inventory:**
    - Call-site 1: [graph_service.py:443](file:///home/cortex/workspace/storyloom/apps/storyloom-api/app/services/graph_service.py#L443)
    - Call-site 2: [update_graph_service.py:43](file:///home/cortex/workspace/storyloom/apps/storyloom-api/app/update_graph_service.py#L43)
  - [x] Corrected 5th argument from `source` to `target`.

### Phase 2: Database Migration & Cleanup

- [x] **Step 2.1:** Execute pre-purge validation query.
  - **Count:** 3,260 self-loops.
- [x] **Step 2.2:** Purge self-loops using:
  ```cypher
  MATCH (n)-[r]->(n) DELETE r
  ```
- [x] **Step 2.3:** Execute post-purge validation query.
  - **Count:** 0 self-loops.

### Phase 3: Ingestion Re-run

- [x] **Step 3.1:** Re-import `fifa_world_cup_2026_eng` and `fifa_world_cup_2026_esp` packs to verify correct relationships are created.
  - **Validation:** Executed `MATCH (p:Person)-[r]->(t:Team)` and confirmed relationships connect Player nodes to Team nodes.

---

**Implementation Completed:** 2026-07-22 14:08 UTC  
**Validated By:** Antigravity  
**Success Status:** Success  

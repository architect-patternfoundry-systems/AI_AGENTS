# Implementation Checklist - Avatar Pipeline Fixes

**Created:** 2026-07-22  
**Target Deployment:** 2026-07-22  
**System/Component:** Avatar Pipeline  
**Change Type:** Code / Infrastructure  
**Risk Level:** Low  
**Agent:** Antigravity

---

## Overview

**Purpose:** Fix connection leakage, eliminate rembg cache retrieval timeouts, and restore candidate image visibility in the frontend.  
**Scope:** `generative.py`, `avatar_generator.py`, `mediaUtils.js`, and `NarrativeGraphCanvas.jsx`.  
**Success Criteria:** Avatars generate without warnings, remove backgrounds instantly, and show up on the frontend canvas and review modal.

---

## Implementation Steps

### Phase 1: Connection Leak Cleanup

- [x] **Step 1.1:** Add `aclose()` implementation in [generative.py](file:///home/cortex/workspace/storyloom/apps/storyloom-api/app/services/generative.py).
- [x] **Step 1.2:** Call `aclose()` in the `finally` block of `generate_base_image` in [avatar_generator.py](file:///home/cortex/workspace/storyloom/apps/storyloom-api/app/services/avatar_generator.py).

### Phase 2: Rembg Cache Linking

- [x] **Step 2.1:** Create `.u2net/` directory and symlink `u2net.onnx` inside the running api container.

### Phase 3: Frontend URL Resolution

- [x] **Step 3.1:** Prepend `/v1/asset/` to S3 prefixes (`temp/`, `character_avatar/`) in `mediaUtils.js` and `NarrativeGraphCanvas.jsx`.
- [x] **Step 3.2:** Wrap candidate image URLs in `resolveMediaUrl()` in `CharacterStudio.jsx`.

---

**Implementation Completed:** 2026-07-22 15:33 UTC  
**Validated By:** Antigravity  
**Success Status:** Success  

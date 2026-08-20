# Incident Report - Avatar Pipeline Timeouts & Serving Leaks

**Date:** 2026-07-22  
**System/Component:** Avatar Pipeline / frontend-backend integrations  
**Severity:** High  
**Status:** Resolved  
**Agent:** Antigravity

---

## Executive Summary

During avatar generation, the backend system logged socket leak warnings (`Unclosed client session`), timed out during background removal (`rembg` fallback), and failed to render generated candidate images on the frontend. Investigation revealed:
1. `aiohttp.ClientSession` instances used in `A1111DirectAdapter` were never closed, causing socket leaks.
2. `rembg` attempted to download the `u2net.onnx` model over the internet because the local file was located in the parent directory `/root/.cache/huggingface/rembg/` rather than the required subdirectory `.u2net/`.
3. S3 keys (`temp/...` and `character_avatar/...`) returned by the backend were requested directly by the frontend, bypassing the necessary proxy route `/v1/asset/`.

These issues were resolved by closing client sessions, symlinking the `u2net.onnx` file, and updating the frontend to prepend `/v1/asset/` to S3 keys.

---

## Problem Statement

**Initial Issue:**
- Avatar generation logs reported `Unclosed client session` warnings.
- Background removal hung and timed out after 15s.
- Generated images failed to display on the frontend.

**Affected Systems:**
- `storyloom-api` (Inference adapter and background removal executor)
- `storyloom-web` (Roster/Review visual grid and graph canvas)

**Impact Assessment:**
- **Business Impact:** Blocked visual review loops, rendering character studios and visual representations broken.
- **Data Impact:** None. Files were generated in MinIO but inaccessible to the client.

---

## Investigation Findings

### Initial Assessment

**Discovery Method:** User log submission from Tiltlog and frontend reports.

### Investigation Process

**Steps Taken:**
1. Audited `generative.py` and found `nanny_session` was instantiated per adapter construct but never closed inside `aclose()`.
2. Inspected the pod cache and confirmed `/root/.cache/huggingface/rembg/u2net.onnx` existed, but verified `rembg` appends `.u2net/u2net.onnx` relative to `U2NET_HOME`.
3. Verified the ingress did not routing `/temp/` or `/character_avatar/` paths to any pod, and confirmed `/v1/asset/<key>` handles proxying.

---

## Root Cause Analysis

### Primary Root Causes

1. **Memory & Connection Leak:** `A1111DirectAdapter` leaked ClientSessions, causing connection congestion and eventually ready probe timeouts.
2. **Directory Mismatch:** `rembg` looked for `$U2NET_HOME/.u2net/u2net.onnx` but the cache volume only populated `u2net.onnx` in the base path.
3. **Missing URL Resolution:** Frontend components rendered raw S3 keys without the `/v1/asset/` proxy prefix.

---

## Resolution Actions

### Immediate Actions

**Action 1 (Client Session):**
Closed the `nanny_session` in `A1111DirectAdapter.aclose()` and ensured it is called in `finally` blocks.

**Action 2 (Rembg):**
Created the `.u2net` directory and symlinked `u2net.onnx` inside the container:
```bash
mkdir -p /root/.cache/huggingface/rembg/.u2net
ln -sf /root/.cache/huggingface/rembg/u2net.onnx /root/.cache/huggingface/rembg/.u2net/u2net.onnx
```

**Action 3 (Proxy Route):**
Modified `resolveMediaUrl` in `mediaUtils.js` and `resolvePortraitUrl` in `NarrativeGraphCanvas.jsx` to prepend `/v1/asset/` to S3 paths.

---

## Validation Results

### Testing Performed

- Candidate avatar generation executed for England team players.
- Verified background removal completed in ~1-2 seconds (zero timeouts).
- Verified logs contain no `Unclosed client session` warnings.
- Verified candidates display successfully in the client interface.

---

**Report Completed:** 2026-07-22 15:32 UTC  
**Archive Date:** 2026-08-22  

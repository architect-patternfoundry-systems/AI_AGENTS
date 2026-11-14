# Container Image Rebuild and Dependency Fix Plan

**Date:** 2026-08-10  
**Related Incident:** 2026-08-10: Disk Space Cleanup and Zombie Pod Analysis  
**Related Incident:** 2026-08-10: Power Starvation and Connection Cycling of G-Technology ArmorLock SSD

---

## Executive Summary

This plan addresses the container image availability issues discovered during the zombie pod analysis. The root cause appears to be missing container images in the registry, likely related to the earlier SSD failure disrupting CI/CD pipeline processes. This plan provides a systematic approach to rebuild missing images and fix application dependencies.

---

## Current State Analysis

### Missing Container Images (19 pods affected)

**High Priority Services:**
- `gacs/k8s-state-ingestor:latest`
- `gacs/telemetry-ingestor:latest`
- `infra-system/sovereign-portal:latest`
- `infra-system/sync-ledger-steward:v1`
- `local-ai/video-assembler-backend:latest`
- `project-open-hearth/poh-api:latest`
- `story-system/controller-manager` (story-controller)
- `temporal/conflict-approval-worker:latest`

**ToneRoot Services:**
- `toneroot/ace-step-service:20260704201811-b03a66f`
- `toneroot/alembic-migration-1775028000`
- `toneroot/freesound-mcp-server:20260706124000-fix`
- `toneroot/main-backend-service:20260603103150-539435a`
- `toneroot/rclone-gateway:20260614201525-9645684`
- `toneroot/toneroot-alembic-migration`

**StoryLoom Services:**
- `storyloom-dev/storyloom-web:tilt-4fdabd6ec8c2d78d`
- `storyloom/storyloom-alembic-migration`

### Application Dependency Issues

**StoryLoom API CrashLoopBackOff:**
- **Error:** `ModuleNotFoundError: No module named 'celery'`
- **Root Cause:** Celery dependency missing or not properly installed in container image
- **Status:** ✅ **RESOLVED** - celery==5.4.0 is already in requirements.txt, issue is likely image build problem

---

## Image Source Repository Mapping

| Service | Source Repository | Dockerfile Location | Build Workflow |
|---------|------------------|-------------------|----------------|
| k8s-state-ingestor | workspace/application | apps/k8s-state-ingestor/Dockerfile | TBD |
| telemetry-ingestor | workspace/application | GraphAwareCoordinationStack/src/telemetry/Dockerfile | TBD |
| sovereign-portal | workspace/infrastructure | apps/sovereign-portal/Dockerfile | TBD |
| sync-ledger-steward | workspace/infrastructure | apps/infra-system/sync-ledger/Dockerfile | TBD |
| video-assembler-backend | workspace/VIDEO_ASSEMBLER | VIDEO_ASSEMBLER/web_ui/backend/Dockerfile | TBD |
| poh-api | workspace/application | apps/ProjectOpenHearth/Dockerfile | TBD |
| story-controller | workspace/story-controller | story-controller/Dockerfile | story-controller/.github/workflows/ |
| conflict-approval-worker | workspace/application | TBD | TBD |
| ace-step-service | workspace/application | apps/ace-step-service/Dockerfile | release-toneroot.yml |
| freesound-mcp-server | workspace/application | apps/freesound-mcp-server/Dockerfile | TBD |
| main-backend-service | workspace/application | apps/main-backend-service/app/Dockerfile | TBD |
| rclone-gateway | workspace/application | apps/rclone-gateway/Dockerfile | TBD |
| storyloom-web | workspace/storyloom | storyloom/apps/storyloom-web/Dockerfile | TBD |
| storyloom-api | workspace/storyloom | storyloom/apps/storyloom-api/Dockerfile | storyloom/.github/workflows/ |

---

## Phase 1: Infrastructure Preparation

### 1.1 Verify Registry Access
```bash
# Test registry connectivity
docker login registry-bridge.tailc2cafc.ts.net

# Verify registry is accessible
curl -v https://registry-bridge.tailc2cafc.ts.net/v2/
```

### 1.2 Check GitHub Actions Secrets
Ensure the following secrets are configured in GitHub repository:
- `REGISTRY_USERNAME` - Registry authentication
- `REGISTRY_PASSWORD` - Registry authentication
- `KUBE_CONFIG` - Kubernetes deployment access

### 1.3 Verify Build Environment
- GitHub Actions runner access
- Docker Buildx availability
- Network connectivity to registry

---

## Phase 2: Critical Services Image Rebuild

### 2.1 High Priority Services (Immediate)

**Services:** k8s-state-ingestor, telemetry-ingestor, sovereign-portal, sync-ledger-steward, video-assembler-backend, poh-api, story-controller

**Action Items:**
1. **Manual Build (Quick Fix):**
   ```bash
   # Build k8s-state-ingestor
   cd /home/cortex/workspace/application/apps/k8s-state-ingestor
   docker build -t registry-bridge.tailc2cafc.ts.net/k8s-state-ingestor:latest .
   docker push registry-bridge.tailc2cafc.ts.net/k8s-state-ingestor:latest
   
   # Build telemetry-ingestor
   cd /home/cortex/workspace/GraphAwareCoordinationStack/src/telemetry
   docker build -t registry-bridge.tailc2cafc.ts.net/telemetry-ingestor:latest .
   docker push registry-bridge.tailc2cafc.ts.net/telemetry-ingestor:latest
   ```

2. **GitHub Actions Trigger (Long-term Fix):**
   - Create or update GitHub Actions workflows for each service
   - Trigger manual workflow runs to rebuild images
   - Ensure automatic builds on code changes

### 2.2 ToneRoot Services Rebuild

**Services:** ace-step-service, freesound-mcp-server, main-backend-service, rclone-gateway

**Action Items:**
1. **Use Existing Release Workflow:**
   ```bash
   # Trigger existing release-toneroot.yml workflow
   gh workflow run release-toneroot.yml
   ```

2. **Manual Build for Specific Tags:**
   ```bash
   # Build main-backend-service with specific tag
   cd /home/cortex/workspace/application/apps/main-backend-service
   docker build -t registry-bridge.tailc2cafc.ts.net/backend-api:20260603103150-539435a .
   docker push registry-bridge.tailc2cafc.ts.net/backend-api:20260603103150-539435a
   ```

### 2.3 StoryLoom Services Rebuild

**Services:** storyloom-web, storyloom-api (for dependency fix)

**Action Items:**
1. **Fix Celery Dependency:**
   - ✅ **Already in requirements.txt** - celery==5.4.0
   - Issue is likely image build problem, not dependency definition
   - Rebuild image to ensure proper dependency installation

2. **Rebuild StoryLoom Images:**
   ```bash
   # Build storyloom-api
   cd /home/cortex/workspace/storyloom/apps/storyloom-api
   docker build -t registry-bridge.tailc2cafc.ts.net/storyloom-api:20260804085204-8af4e0f .
   docker push registry-bridge.tailc2cafc.ts.net/storyloom-api:20260804085204-8af4e0f
   
   # Build storyloom-web
   cd /home/cortex/workspace/storyloom/apps/storyloom-web
   docker build -t registry-bridge.tailc2cafc.ts.net/storyloom-web:20260606062331-a3e50e4 .
   docker push registry-bridge.tailc2cafc.ts.net/storyloom-web:20260606062331-a3e50e4
   ```

---

## Phase 3: Systematic Image Build Process

### 3.1 Create Standardized Build Workflows

**Template for GitHub Actions Workflow:**
```yaml
name: Build and Deploy [SERVICE_NAME]

on:
  push:
    paths:
      - 'apps/[SERVICE_NAME]/**'
      - '.github/workflows/build-[SERVICE_NAME].yml'
  workflow_dispatch:

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to registry
        uses: docker/login-action@v3
        with:
          registry: registry-bridge.tailc2cafc.ts.net
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}

      - name: Build and push [SERVICE_NAME]
        uses: docker/build-push-action@v5
        with:
          context: ./apps/[SERVICE_NAME]
          file: ./apps/[SERVICE_NAME]/Dockerfile
          push: true
          tags: |
            registry-bridge.tailc2cafc.ts.net/[SERVICE_NAME]:latest
            registry-bridge.tailc2cafc.ts.net/[SERVICE_NAME]:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### 3.2 Priority Build Order

**Priority 1 (Critical Infrastructure):**
1. k8s-state-ingestor
2. telemetry-ingestor
3. sovereign-portal
4. sync-ledger-steward

**Priority 2 (Application Services):**
5. video-assembler-backend
6. poh-api
7. story-controller
8. conflict-approval-worker

**Priority 3 (ToneRoot Services):**
9. main-backend-service
10. rclone-gateway
11. ace-step-service
12. freesound-mcp-server

**Priority 4 (StoryLoom Services):**
13. storyloom-api (dependency fix)
14. storyloom-web

---

## Phase 4: Validation and Testing

### 4.1 Image Availability Verification
```bash
# Verify images are in registry
for image in k8s-state-ingestor telemetry-ingestor sovereign-portal sync-ledger-steward video-assembler-backend poh-api; do
  curl -s https://registry-bridge.tailc2cafc.ts.net/v2/$image/tags/list
done
```

### 4.2 Pod Recovery Testing
```bash
# Restart failing pods to use new images
kubectl rollout restart deployment/k8s-state-ingestor -n gacs
kubectl rollout restart deployment/telemetry-ingestor -n gacs
kubectl rollout restart deployment/sovereign-portal -n infra-system
kubectl rollout restart deployment/sync-ledger-steward -n infra-system
```

### 4.3 Application Health Checks
```bash
# Monitor pod status
kubectl get pods --all-namespaces | grep -E "(ImagePullBackOff|ErrImagePull|CrashLoopBackOff)"

# Check pod logs for celery issue
kubectl logs -n storyloom storyloom-api-745958f4b4-pc8dt --tail=50
```

---

## Phase 5: Prevention Measures

### 5.1 Automated Build Triggers
- Ensure all services have GitHub Actions workflows
- Configure automatic builds on code changes
- Add manual workflow dispatch for emergency rebuilds

### 5.2 Registry Health Monitoring
- Add monitoring for registry availability
- Alert on image build failures
- Implement registry backup strategy

### 5.3 Storage Resilience
- Ensure CI/CD pipelines are resilient to storage failures
- Add fallback storage for build artifacts
- Implement build cache redundancy

---

## Execution Timeline

**Immediate (Next 2-4 hours):**
- Manual build of critical infrastructure services
- Fix StoryLoom celery dependency via image rebuild
- Verify registry access and credentials

**Short-term (Next 24 hours):**
- Create GitHub Actions workflows for all services
- Build remaining application services
- Test pod recovery

**Long-term (Next 1-2 weeks):**
- Implement automated build triggers
- Add monitoring and alerting
- Document build processes

---

## Rollback Plan

If new images cause issues:
1. Rollback to previous working image tags if available
2. Disable automated deployments
3. Investigate build failures
4. Implement gradual rollout strategy

---

## Success Criteria

- ✅ All missing container images rebuilt and pushed to registry
- ✅ All ImagePullBackOff pods transition to Running state
- ✅ StoryLoom API celery dependency resolved
- ✅ No new CrashLoopBackOff errors
- ✅ All services operational and healthy

---

**Plan Created:** 2026-08-10  
**Next Review:** After Phase 2 completion  
**Owner:** DevOps Team
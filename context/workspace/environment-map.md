# Environment Architecture Map

**Last Updated:** 2026-06-03  
**Domain:** tailc2cafc.ts.net  
**Purpose:** Comprehensive mapping of all environments, services, URLs, namespaces, and shared components

---

## 1. Tailscale URLs by Environment

### ToneRoot (Audio/Media Application)

| Environment | URL | Status | Database |
|-------------|-----|--------|----------|
| **Development** | https://toneroot-dev.tailc2cafc.ts.net/ | Active | toneroot-dev |
| **Pre-Production** | https://toneroot-preprod.tailc2cafc.ts.net/ | Active | toneroot-preprod |
| **Production** | (Not deployed) | - | - |

### StoryLoom (Story Generation Platform)

| Environment | URL | Status | Database |
|-------------|-----|--------|----------|
| **Development** | (Tilt local) | - | storyloom-dev |
| **Pre-Production** | https://storyloom-preprod.tailc2cafc.ts.net/ | Active | storyloom |
| **Production** | (Not deployed) | - | - |

### Infrastructure & Governance

| Service | URL | Purpose |
|---------|-----|---------|
| **GACS Topology** | https://gacs.tailc2cafc.ts.net/ | Governance, Audit, Compliance System |
| **BRL Dashboard** | https://brl-dashboard.tailc2cafc.ts.net/ | Cluster Health & Remediation |
| **Registry** | registry-bridge.tailc2cafc.ts.net:5000 | Container Image Registry |
| **MinIO Console** | https://minio-console.tailc2cafc.ts.net/ | S3-Compatible Object Storage |
| **Grafana** | https://grafana.tailc2cafc.ts.net/ | Metrics & Dashboards |
| **Traefik Dashboard** | (Internal cluster access) | Ingress Controller |

---

## 2. Codebase Structure

### Repository: `application`

```
/home/cortex/workspace/application/
├── apps/
│   ├── toneroot/                    # ToneRoot Audio Platform
│   │   ├── web/
│   │   │   ├── backend/            # FastAPI Backend
│   │   │   ├── frontend/           # React Frontend
│   │   │   └── worker/             # Celery Worker
│   │   ├── Tiltfile               # Local dev environment
│   │   ├── migrations/            # Alembic migrations
│   │   └── Dockerfile.*           # Multi-stage builds
│   │
│   ├── storyloom/                  # StoryLoom Platform
│   │   ├── apps/
│   │   │   ├── web/               # Next.js Frontend
│   │   │   ├── api/               # FastAPI Backend
│   │   │   └── worker/            # Background jobs
│   │   └── Tiltfile              # Local dev environment
│   │
│   ├── f5-tts-service/            # Text-to-Speech Service
│   ├── whisper-worker/            # Audio Transcription
│   ├── synthesis-worker/          # Audio Synthesis
│   ├── gpu-nanny-controller/    # GPU Resource Management
│   ├── local-image-worker-service/  # Image Processing
│   ├── freesound-mcp-server/    # Freesound Integration
│   └── [other services...]
│
├── app_lib/                        # Shared Libraries (Root level)
│   ├── usagelogger.py             # Usage tracking utilities
│   └── [other shared utilities]
│
├── applib/                         # Database connection utilities
│   ├── dbconnection.py            # DB connection management
│   └── __init__.py
│
├── sharedmodels.py                 # Shared Pydantic/SQLAlchemy models
│
├── migrations/                     # Global migrations (if any)
│
├── .github/workflows/              # CI/CD Workflows
│   ├── build-toneroot-backend.yaml
│   ├── build-toneroot-frontend.yaml
│   ├── build-toneroot-worker.yaml
│   ├── build-storyloom-*.yaml
│   └── [reusable workflows]
│
└── [root-level scripts and configs]
```

### Repository: `infrastructure`

```
/home/cortex/workspace/infrastructure/
├── apps/
│   ├── toneroot/                  # ToneRoot K8s manifests
│   │   ├── app/
│   │   │   ├── deployment.yaml   # Base deployment
│   │   │   └── service.yaml
│   │   ├── overlays/
│   │   │   ├── dev/             # Dev environment
│   │   │   └── preprod/         # Preprod environment
│   │   │       ├── ingress.yaml
│   │   │       ├── migration-job.yaml
│   │   │       └── kustomization.yaml
│   │   └── image-policy.yaml    # Flux ImagePolicy
│   │
│   ├── storyloom/               # StoryLoom K8s manifests
│   │   ├── base/
│   │   └── overlays/
│   │       └── preprod/
│   │
│   ├── gacs/                    # Governance System
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── span-processor-configmap.yaml
│   │
│   ├── infra-system/            # Shared Infrastructure
│   │   ├── registry-local/      # Container registry
│   │   ├── brl-dashboard/     # Cluster health dashboard
│   │   ├── sync-ledger/       # Service sync
│   │   ├── pypi-server/       # Python package mirror
│   │   └── coredns.yaml       # DNS configuration
│   │
│   ├── postgres/                # PostgreSQL manifests
│   ├── pgbouncer/               # Connection pooler
│   ├── minio/                   # Object storage
│   ├── traefik-helmrelease.yaml # Ingress controller
│   ├── cert-manager/            # TLS certificates
│   ├── observability/           # Monitoring stack
│   │   ├── prometheus/
│   │   ├── grafana/
│   │   ├── loki/
│   │   └── tempo/
│   │
│   └── [other infrastructure components...]
│
├── kustomization.yaml           # Root kustomization
└── [global patches and configs]
```

---

## 3. Kubernetes Namespaces

### Application Namespaces

| Namespace | Purpose | Owner | Critical Services |
|-----------|---------|-------|-------------------|
| `toneroot` | ToneRoot Application | ToneRoot Team | Backend, Frontend, Worker |
| `storyloom` | StoryLoom Application | StoryLoom Team | API, Web, Worker |
| `storyloom-preprod` | StoryLoom Preprod | StoryLoom Team | Preprod deployment |

### Infrastructure Namespaces

| Namespace | Purpose | Owner | Shared Components |
|-----------|---------|-------|-------------------|
| `infra-data` | Shared Data Layer | Platform Team | PostgreSQL, PgBouncer |
| `minio` | Object Storage | Platform Team | MinIO S3-compatible storage |
| `observability` | Monitoring Stack | Platform Team | Prometheus, Grafana, Loki, Tempo |
| `gacs` | Governance & Audit | Platform Team | Span Processor, Neo4j |
| `kube-system` | Kubernetes System | Kubernetes | CoreDNS, CNI (Cilium/Flannel) |
| `flux-system` | GitOps | Platform Team | FluxCD controllers |
| `tailscale` | Networking | Platform Team | Tailscale operator, proxies |
| `cert-manager` | TLS Certificates | Platform Team | cert-manager |
| `traefik` | Ingress Controller | Platform Team | Traefik |
| `registry-local` | Container Registry | Platform Team | Docker registry |
| `pypi-server` | Python Packages | Platform Team | PyPI mirror |

### Specialized Namespaces

| Namespace | Purpose |
|-----------|---------|
| `f5-tts-service` | Text-to-Speech workloads |
| `whisper-worker` | Audio transcription |
| `synthesis-worker` | Audio synthesis |
| `gpu-nanny-controller` | GPU resource management |
| `freesound-mcp-server` | Freesound integration |
| `stable-diffusion-webui` | Image generation |
| `alltalk-tts` | Alternative TTS service |
| `sillytavern` | AI character interactions |
| `sovereign-portal` | Admin portal |
| `governance-service` | Policy enforcement |
| `maintenance` | Maintenance jobs |
| `dynamic-dns` | DNS management |
| `rclone-gateway` | Cloud sync |
| `nfs-provisioner` | NFS storage |
| `local-image-worker-service` | Image processing |
| `backend` | Shared backend services |
| `story-controller` | Story orchestration |
| `render-guard` | Rendering management |
| `ingress-global` | Global ingress rules |
| `resource-constraints` | Resource policies |
| `shared-substrate` | Shared substrate |
| `secrets` | Secret management |
| `governance-policies` | Policy definitions |
| `tailscale-operator` | Tailscale management |

---

## 4. Database Mapping

### PostgreSQL Databases

| Database Name | Application | Environment | Owner |
|---------------|-------------|-------------|-------|
| `toneroot-preprod` | ToneRoot | Pre-Production | toneroot-backend |
| `toneroot-dev` | ToneRoot | Development | toneroot-backend |
| `storyloom` | StoryLoom | Pre-Production | storyloom-api |
| `storyloom-dev` | StoryLoom | Development | storyloom-api |
| `mydatabase` | Legacy/Other | - | Various |

### Connection Path

```
Application Pod → PgBouncer (infra-data) → PostgreSQL (infra-data)
                    ↓
              Connection Pooling
```

**PgBouncer Service:** `pgbouncer.infra-data.svc.cluster.local:5432`

---

## 5. Tiltfile Configuration

### ToneRoot Tiltfile

**Location:** `/home/cortex/workspace/application/apps/toneroot/Tiltfile`

**Purpose:** Local development environment using Tilt

**Services:**
- Backend (FastAPI on port 8001)
- Frontend (React dev server)
- Worker (Celery)
- PostgreSQL (local container)
- Redis (for Celery)

**Key Features:**
- Live reload for backend/frontend
- Local database for development
- Resource dependencies (db before app)

### StoryLoom Tiltfile

**Location:** `/home/cortex/workspace/application/apps/storyloom/Tiltfile`

**Purpose:** Local development for StoryLoom platform

---

## 6. GitHub Workflows

### Location: `/home/cortex/workspace/application/.github/workflows/`

### ToneRoot Workflows

| Workflow | Purpose | Triggers |
|----------|---------|----------|
| `build-toneroot-backend.yaml` | Build & push backend image | Push to main (backend paths) |
| `build-toneroot-frontend.yaml` | Build & push frontend image | Push to main (frontend paths) |
| `build-toneroot-worker.yaml` | Build & push worker image | Push to main (worker paths) |

### StoryLoom Workflows

| Workflow | Purpose | Triggers |
|----------|---------|----------|
| `build-storyloom-api.yaml` | Build API service | Push to main |
| `build-storyloom-web.yaml` | Build web frontend | Push to main |
| `build-storyloom-worker.yaml` | Build worker | Push to main |

### Infrastructure Updates

**Note:** Image tags are managed by **FluxCD ImageUpdateAutomation** using `$imagepolicy` markers in deployment manifests, NOT by GitHub Actions directly pushing to the infrastructure repo.

---

## 7. Shared Components & Services

### Tier 1: Core Infrastructure (Required by all apps)

| Component | Namespace | Purpose | Dependencies |
|-----------|-----------|---------|--------------|
| **PostgreSQL** | infra-data | Primary database | NFS storage |
| **PgBouncer** | infra-data | Connection pooling | PostgreSQL |
| **MinIO** | minio | S3-compatible storage | NFS storage |
| **CoreDNS** | kube-system | Internal DNS | - |
| **Tailscale Operator** | tailscale | VPN mesh networking | Host DNS |
| **Registry** | registry-local | Image storage | - |

### Tier 2: Observability (Used by most apps)

| Component | Namespace | Purpose |
|-----------|-----------|---------|
| **Prometheus** | observability | Metrics collection |
| **Grafana** | observability | Dashboards & alerts |
| **Loki** | observability | Log aggregation |
| **Tempo** | observability | Distributed tracing |

### Tier 3: Application-Specific (Shared within domains)

| Component | Namespace | Used By |
|-----------|-----------|---------|
| **GACS Span Processor** | gacs | All apps (topology) |
| **Neo4j** | gacs | GACS (graph storage) |
| **BRL Dashboard** | infra-system | Operations team |
| **Sync Ledger** | infra-system | All apps (service discovery) |

---

## 8. Shared Libraries

### Location: `/home/cortex/workspace/application/`

| Library | Path | Purpose | Used By |
|---------|------|---------|---------|
| **sharedmodels.py** | Root level | Shared Pydantic/SQLAlchemy models | All apps |
| **usagelogger.py** | app_lib/ | Usage tracking utilities | All apps |
| **dbconnection.py** | applib/ | Database connection management | All apps |

### Migration Pattern

**Location:** `/home/cortex/workspace/application/apps/{app}/migrations/versions/`

- Uses Alembic for database migrations
- Each app manages its own migrations
- Migrations run as Kubernetes Jobs during deployment

---

## 9. Environment Isolation Strategy

### Development (Tilt)

- **Local Kubernetes** (k3d/minikube/kind)
- **Local PostgreSQL** container
- **Local MinIO** container
- **Hot reload** for code changes
- **No Tailscale** (localhost access)

### Pre-Production (Preprod)

- **Shared Kubernetes cluster**
- **Shared PostgreSQL** (dedicated database per app)
- **Shared MinIO** (dedicated bucket per app)
- **Tailscale ingress** (*.tailc2cafc.ts.net)
- **FluxCD GitOps** deployment

### Production (Not Yet Deployed)

- Would follow preprod pattern with:
  - Separate cluster or node pool
  - Higher resource limits
  - Additional backup/DR
  - Separate Tailscale domain

---

## 10. Network Architecture

### Tailscale Mesh

```
Internet
    ↓
Tailscale DERP (relay)
    ↓
Tailscale Proxy Pod (ts-*)
    ↓
Traefik Ingress Controller
    ↓
Application Service (ClusterIP)
    ↓
Application Pod
```

### Internal Service Communication

```
Pod A → CoreDNS → Service B → Pod B

DNS Format: {service}.{namespace}.svc.cluster.local
Example: pgbouncer.infra-data.svc.cluster.local
```

### Database Flow

```
Application Pod
    ↓
PgBouncer Service (infra-data)
    ↓
PostgreSQL Pod (infra-data)
```

---

## 11. Quick Reference Commands

### Database Operations

```bash
# List all databases
kubectl exec -n infra-data deployment/postgres -- psql -U cortex_db_admin -c "\l"

# Connect to specific database
kubectl exec -n infra-data deployment/postgres -- psql -U cortex_db_admin -d toneroot-preprod

# Run migrations
kubectl apply -f infrastructure/apps/toneroot/overlays/preprod/migration-job.yaml
```

### Pod Debugging

```bash
# Check pod status
kubectl get pods -n toneroot

# View logs
kubectl logs -n toneroot deployment/toneroot-backend

# Execute into pod
kubectl exec -n toneroot deployment/toneroot-backend -c toneroot-backend -- /bin/sh
```

### Service Discovery

```bash
# List services
kubectl get svc -n toneroot

# Check endpoints
kubectl get endpoints -n toneroot

# Test connectivity
kubectl run -n toneroot test --image=busybox --rm -it -- wget -O- http://toneroot-backend:8001/health
```

---

## 12. Troubleshooting Matrix

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `nc: bad address 'pgbouncer...'` | DNS/CoreDNS issue | Check CoreDNS pods, host DNS |
| `FATAL: client_login_timeout` | PgBouncer can't reach Postgres | Check network policies, pod placement |
| `too many clients already` | Connection limit reached | Restart PgBouncer, check pool config |
| ImagePullBackOff | Registry/tailscale issue | Check ts-proxy pods, registry health |
| CrashLoopBackOff | App error or missing deps | Check logs, verify migrations |

---

## 13. Related Documentation

- [Infrastructure Standards](../../global/infrastructure.md)
- [Operations Runbook](../../global/operations.md)
- [ADR-013: Drop-Folder Worker](../../global/adr/ADR-013-drop-folder-worker.md)
- [ADR-014: Ingestion Gateway](../../global/adr/ADR-014-ingestion-gateway.md)
- [Cluster Health BRL Dashboard](../../infrastructure/docs/cluster-health-brl-dashboard-sdd.md)

---

## Appendix: Database Schema Notes

### Migration 0005: `add_byob_storage_configs.py`

Creates `storage_configs` table for per-user S3 credentials:

```sql
CREATE TABLE storage_configs (
    uuid UUID PRIMARY KEY,
    profile_uuid UUID REFERENCES users(id),  -- Per-user config
    storage_type VARCHAR(50),  -- 's3', 'minio'
    bucket_name VARCHAR(255),
    endpoint_url VARCHAR(500),
    access_key VARCHAR(255),     -- User's S3 access key
    secret_key VARCHAR(255),     -- User's S3 secret key
    region VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Migration 0006: `unify_identity_model.py`

Updates `users` table:
- Adds `is_admin` boolean column
- Links to `storage_configs.profile_uuid`

---

*Document maintained by AI Agents. Update when adding new environments, services, or changing architecture.*

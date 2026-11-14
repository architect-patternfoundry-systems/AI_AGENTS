# New Service Onboarding Checklist
## Sovereign Cluster

This checklist is the standard onboarding template for new microservices in the Sovereign cluster. It is organized into three sections:

- **Required for all services**.
- **Required for GPU / ML inference services**.
- **Optional or conditional items**.

Use it for services such as `f5-tts`, `fish-speech`, Whisper-based workers, and other internal workloads that must operate under zero-trust, GitOps-managed, observability-driven constraints.

***

## 1. Required for all services

- [ ] **Dockerization**
  - Create a production-ready `Dockerfile` with optimized layers.
  - Use a reproducible base image and keep the runtime image as small as practical.
  - **GPU/CUDA Optimization**: Leverage pre-built layers from `registry-bridge.tailc2cafc.ts.net` (e.g., `acestep-prebuilt`) for heavy CUDA compilations like `flash-attn` and `xformers` instead of using slow multi-stage compiles from source.
  - If the service depends on large assets or models, document whether they are bundled at build time or mounted from persistent storage.

- [ ] **GitHub Actions workflow**
  - Add a `.github/workflows/build-service.yaml` workflow for container builds.
  - Use `docker/setup-buildx-action` and push to the designated registry.
  - Grant only the permissions required for the registry and checkout steps.

- [ ] **FluxCD registration**
  - Add the new service directory to `apps/kustomization.yaml`.
  - Include `deployment.yaml`, `service.yaml`, and any supporting manifests in the service directory.
  - Ensure image tags or digests are updated through GitOps, not manual cluster edits.

- [ ] **Deployment manifest**
  - Define `replicas`, resource requests, and resource limits explicitly.
  - Set `serviceAccountName` to a dedicated service account.
  - Mount only the volumes the service actually needs.
  - Add labels that make ownership and observability easier.

- [ ] **Service manifest**
  - Create a `ClusterIP` service for internal routing.
  - Expose only the ports required by internal callers.

- [ ] **Governance & Criticality (Cynefin Ledger)**
  - Score the new service across the **5 Lenses** (Availability, Latency, Blast Radius, Data Integrity, Security).
  - If the service is deemed critical, record its identity, SLO, and lens weights in `docs/CYNEFIN_LEDGER.md`.
  - Define the correct **SLO contract** based on the workload architecture:
    - *Stateless Control Plane:* Define standard Uptime/Availability targets.
    - *GPU/Ephemeral Workload:* Define Time-to-Acquisition and Cold-Start latency targets.
  - Register the canonical routing identity via Tailscale MagicDNS (`*.tailc2cafc.ts.net`).
  - Document the service owner and operational contact for alerts.

- [ ] **Config and secrets**
  - Store runtime configuration outside the image.
  - Use ConfigMaps, Secrets, or mounted files for environment-specific values.
  - Document which settings are required for local, staging, and production use.

- [ ] **Security baseline**
  - Create a dedicated `ServiceAccount`.
  - Add a `Role` and `RoleBinding` only if the service needs Kubernetes API access.
  - Add a default-deny `NetworkPolicy` and explicitly allow only required ingress and egress.
  - Deny public internet access unless the service has an explicit exception.

- [ ] **Observability**
  - Emit structured logs to stdout/stderr.
  - Add standard Prometheus scrape annotations if the service exposes metrics.
  - Define `livenessProbe` and `readinessProbe`.
  - Make readiness reflect actual request-handling capability, not just process start.

- [ ] **Release and rollback**
  - Define how images are promoted from build to deployment.
  - Document rollback steps for failed releases.
  - Keep rollout strategy compatible with FluxCD and image immutability.

***

## 2. Required for GPU / ML inference services

- [ ] **Inference architecture**
  - Use the service interface required by the workload architecture.
  - For low-latency inference, prefer a direct service API or socket protocol if that is the approved pattern.
  - Document chunking, streaming, or binary-transfer requirements if applicable.

- [ ] **Native model loading**
  - Load models in-process unless a separate serving architecture is explicitly defined.
  - Avoid external proxy subprocesses unless there is a strong reason and a documented exception.
  - Ensure the runtime has direct control over GPU memory management.

- [ ] **GPU resource declaration**
  - Declare GPU limits explicitly, such as `nvidia.com/gpu: "1"` when required.
  - Add any node selectors, tolerations, or affinity rules needed for GPU placement.
  - Verify that the cluster’s GPU device plugin or operator is installed and healthy.

- [ ] **GpuNanny integration**
  - Import and instantiate `GpuNannySteward` or the approved lease client.
  - Wrap inference execution in lease acquisition logic.
  - Ensure the service requests a lease before using the GPU and releases it afterward.
  - Make lease handling idempotent and explicit.

- [ ] **Deterministic unload path**
  - Implement `unload()` or equivalent teardown logic.
  - Release VRAM, clear cached tensors, and collect garbage.
  - Confirm that model teardown happens when the service scales down or loses lease ownership.

- [ ] **Readiness tied to model state**
  - Readiness should succeed only when the model is loaded and the service is actually able to accept work.
  - If the service depends on a lease to operate, readiness should reflect lease state where appropriate.
  - Startup probes should be used if model load time is substantial.

- [ ] **Scale-to-zero behavior**
  - If the service participates in scale-to-zero, define who wakes it up and how.
  - Document whether the service is driven by KEDA, GPU-Nanny, Knative, or a custom control loop.
  - Never mix blind reactive scaling with exclusive GPU lease ownership unless the architecture explicitly supports it.

- [ ] **Model artifact management**
  - Decide whether models are downloaded during image build, on startup, or mounted from persistent storage.
  - Prefer build-time or cached artifact strategies that avoid repeated cold-start downloads where feasible.
  - Document cache location and eviction behavior.

- [ ] **Inference verification**
  - Add a dry-run or smoke test that proves end-to-end model loading and inference.
  - Test lease acquisition, lease release, and preemption behavior.
  - Validate that competing GPU services yield VRAM correctly under contention.

***

## 3. Optional or conditional items

- [ ] **Tailscale exposure**
  - Add Tailscale ingress or service annotations only if the service requires secure external access or direct testing.
  - Keep external exposure off by default.

- [ ] **Binary streaming protocol**
  - Use a socket-based or streaming protocol only when the approved service design requires it.
  - Prefer this for latency-sensitive inference pipelines that benefit from zero-copy transfers.

- [ ] **Persistent model cache volume**
  - Add a HuggingFace or model-cache volume only if the service benefits from it.
  - Document warm-up and cache invalidation behavior.

- [ ] **Competing-service preemption test**
  - Run preemption tests only for GPU services that must yield scarce hardware to another workload.
  - Confirm that the unload path and lease revocation work as expected.

- [ ] **Manual external testing surface**
  - Expose a test-only route or temporary ingress only when the service needs direct operator validation.
  - Remove or disable it after validation unless it is part of the approved design.

***

## 4. Completion criteria

A service is considered onboarded only when all of the following are true:

- It is buildable from GitHub Actions.
- It is deployed through FluxCD.
- It has a dedicated service account and security policy.
- It is observable through logs, metrics, and probes.
- Its runtime behavior matches its orchestration model.
- GPU services have verified lease handling and safe teardown.
- The service owner has confirmed operational readiness.

# ADR 020: GPU Resource Arbitration and Scaling Paradigms

## Status
Proposed

## Context

Our homelab environment operates under strict GPU VRAM constraints while running multiple AI-driven applications, including `ToneRoot` and `StoryLoom`. We currently have two orchestration patterns available: `KEDA`, which reacts to queue depth and scales pods accordingly, and `GPU-Nanny`, which grants lease-based exclusive access to a scarce GPU before workloads are allowed to execute. [docs.cloud.google](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/scale-to-zero-using-keda)

We have observed severe latency in `f5-tts-service` and stalled `whisper-worker` deployments due to uncontrolled contention for GPU memory. When multiple GPU workloads are scaled independently, they can overcommit VRAM, trigger `CUDA OOM` errors, or fall back to CPU execution, which increases latency dramatically and produces unstable behavior. In a single-GPU homelab, scale-to-zero is still desirable, but it must not come at the cost of blind concurrent scheduling. [youtube](https://www.youtube.com/watch?v=V1QS7ec0xg4)

## Decision

We will establish a strict architectural boundary for workload orchestration based on resource profile:

### 1. GPU-bound workloads must use GPU-Nanny

Any service that requires exclusive or effectively exclusive GPU residency must use the `gpu-nanny-controller` for lifecycle arbitration. This includes inference or synthesis services such as Whisper, F5-TTS, and Stable Diffusion, as well as future GPU workloads that cannot safely co-reside in VRAM. [mirantis](https://www.mirantis.com/blog/gpu-infrastructure-automation-and-strategy/)

GPU-bound workers must remain lightweight and always-on at one replica. Before executing a job, the worker must acquire a lease and register intent with GPU-Nanny. The lease is a time-bounded grant of exclusive authority over the GPU, with renewal required until work is complete. If a lease cannot be acquired, the worker must not attempt GPU execution and must instead requeue or defer the job according to service policy. [youtube](https://www.youtube.com/watch?v=Eqeqik5cVfs&vl=en)

KEDA ScaledObjects must not be attached directly to GPU workload deployments. Blind scaling of multiple GPU consumers is incompatible with the physical limits of the node and causes VRAM contention, pod thrash, and degraded performance. [cncf](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/)

### 2. CPU-bound workloads must use KEDA

Stateless, CPU-only tasks that do not require exclusive access to scarce hardware should continue to use KEDA. This includes JSON decoders, text parsers, reconciliation jobs, and other general compute workloads that benefit from reactive queue-based scaling. [developers.redhat](https://developers.redhat.com/articles/2025/08/26/optimize-gpu-utilization-kueue-and-keda)

## Classification rule

A workload is considered **GPU-bound** if it requires GPU execution and cannot tolerate concurrent VRAM contention with other GPU consumers. If a workload can safely run on CPU, tolerate fallback, or be partitioned into an isolated GPU slice with explicit operational support, it must be classified deliberately rather than assumed to fit KEDA by default. [vcluster](https://www.vcluster.com/blog/gpu-multitenancy-kubernetes-strategies)

## Lease semantics

GPU-Nanny leases must define the following behavior:

- **Grant:** exclusive access is assigned to one worker at a time.
- **TTL:** leases expire automatically if not renewed.
- **Renewal:** workers must heartbeat or renew at a fixed interval shorter than TTL.
- **Expiry:** a dead or partitioned worker must lose the lease so another worker can proceed.
- **Crash recovery:** expired leases must be reclaimable without manual intervention.
- **Safety:** downstream actions must be idempotent and fence their writes using the current lease/token or an equivalent version check. [engineersmeetai.substack](https://engineersmeetai.substack.com/p/why-distributed-systems-prefer-leases)

## Consequences

### Positive

- **GPU stability:** prevents concurrent VRAM thrash and reduces `CUDA OOM` failures. [mirantis](https://www.mirantis.com/blog/gpu-infrastructure-automation-and-strategy/)
- **Predictable latency:** avoids unwanted CPU fallback and keeps inference times fast. [engineersmeetai.substack](https://engineersmeetai.substack.com/p/why-distributed-systems-prefer-leases)
- **Scale-to-zero efficiency:** lightweight workers can remain idle while heavy GPU execution only occurs under an active lease. [docs.cloud.google](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/scale-to-zero-using-keda)

### Negative

- **Implementation overhead:** existing GPU workers, including ToneRoot’s `whisper-worker`, must be refactored to adopt the lease workflow instead of direct KEDA scaling.
- **Sequential GPU processing:** GPU workloads across applications will execute one at a time on the available device, which reduces theoretical throughput but matches the available hardware reality. [vcluster](https://www.vcluster.com/blog/gpu-multitenancy-kubernetes-strategies)

## Non-goals

- Concurrent GPU co-scheduling on the single primary GPU is not a goal.
- Blind reactive autoscaling for GPU deployments is not supported.
- CPU fallback as a normal execution path for GPU workloads is not an accepted operating mode. [cncf](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/)

## Migration plan

Existing GPU workloads should be migrated in this order:

1. Remove KEDA ScaledObjects from GPU deployments.
2. Keep one lightweight worker replica running continuously.
3. Add lease acquisition and intent registration before job execution.
4. Add lease renewal and expiry handling.
5. Add retry and deferral behavior for lease contention.
6. Add monitoring for lease wait time, lease expiry, OOM incidence, and queue lag.

## Open questions

- Should GPU-Nanny also provide fencing tokens in addition to leases for downstream safety?
- Should future GPUs with partitioning support, such as MIG-like isolation, be treated as separate arbitration domains?
- Should lease contention emit metrics and alerts separately from normal queue backlog?

## Summary

Use GPU-Nanny for scarce GPU workloads and KEDA for ordinary CPU workloads. The architectural boundary is not about preference; it is about preventing an unsafe autoscaling model from fighting the physical constraints of a single-GPU environment. [linkedin](https://www.linkedin.com/posts/pratikmukane_distributed-locking-7-practical-ways-and-activity-7387375057003515906-mOpF)

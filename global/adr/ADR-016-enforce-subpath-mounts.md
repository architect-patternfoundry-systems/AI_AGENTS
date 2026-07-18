# ADR-016: Enforce SubPath Mounts for Shared Storage

## Status
Accepted

## Context
During an infrastructure update, a `chown -R` operation in an init container intended for a specific application's data directory inadvertently targeted the root mount of a shared host-path Persistent Volume (`/mnt/cluster_storage_ssd`). Because this shared PV also contained Kubernetes system directories like `k3s-data` (used by containerd for overlayfs), the recursive ownership change caused widespread pod failures and node instability as container images were corrupted.

When multiple workloads or cluster-level components share a host-backed volume, mounting the root path directly into a container exposes all adjacent data to container processes. This breaks the principle of least privilege and increases the blast radius of misconfigurations, specifically file permission and deletion scripts commonly found in init containers.

## Decision
We establish the following two hard constraints for all Kubernetes workloads in this workspace:

1. **No Recursive Ownership Changes on Shared Mount Roots**
   Init containers or startup scripts must NEVER run unrestricted recursive commands (like `chown -R` or `rm -rf`) against the root path of a shared mount. All such scripts must include a strict safety guard that:
   - Verifies the target path is not `/` or the direct mount root (e.g., `/ssd`).
   - Ensures the target path is restricted to a specifically scoped namespace or subdirectory.
   - Fails fast if the target path is not a directory.

2. **Isolated Mount Paths or `subPath` Boundaries**
   Any workload using shared storage must mount its volume using a `subPath` boundary or a specifically isolated directory path, rather than mounting the shared root. 
   - **Preferred**: Define a `subPath` in the `volumeMounts` corresponding to the application's unique directory (e.g., `subPath: docker-registry`), and map it to the application's expected data path (e.g., `mountPath: /ssd/docker-registry`). This prevents the container from ever accessing or modifying sibling directories on the shared storage.
   - **Alternative**: If `subPath` cannot be used, the `volumeMounts` must at least append a specific sub-directory to `mountPath` (e.g., `mountPath: /data/app_name`), and the application must be configured to only interact with that specific sub-directory.

## Consequences

### Positive
- Materially reduces the blast radius of rogue container scripts.
- Prevents cross-workload data corruption and cluster-level outages from application-level misconfigurations.
- Promotes explicit storage namespace management.

### Negative
- Requires updating existing manifests and scripts to comply.
- Adds slight complexity to `volumeMounts` and application configuration.

## Implementation Guidelines
### Example of Strict Script Guard
```bash
TARGET="/ssd/docker-registry"
[ -z "$TARGET" ] && echo "TARGET unset, aborting" && exit 1
[ "$TARGET" = "/" ] || [ "$TARGET" = "/ssd" ] || [ "$TARGET" = "/ssd/" ] && echo "Refusing to chown root path" && exit 1

# Ensure we are only operating within the expected mount namespace
if ! echo "$TARGET" | grep -q "^/ssd/docker-registry"; then
    echo "Refusing to operate outside /ssd/docker-registry namespace" && exit 1
fi

if [ -L "$TARGET" ]; then rm "$TARGET"; fi
mkdir -p "$TARGET"

# Fail fast if target is not a directory after creation
[ ! -d "$TARGET" ] && echo "Target is not a directory, aborting" && exit 1

chown -R 1000:1000 "$TARGET"
```

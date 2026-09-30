# Workspace Context Overrides

Workspace-specific overrides and additions to global governance.

## Workspace-Specific Paths
- Workspace root: `/home/cortex/workspace`
- Shared storage: `/mnt/data_lake`
- NFS server: `cortex.tailc2cafc.ts.net`

## Workspace-Specific Tools
- CUDA path: `/usr/local/lib/ollama/cuda_v12/`
- Tailscale subnet: `100.64.0.0/10`
- LAN subnet: `192.168.86.0/24`

## Workspace-Specific Policies
- All services must use Tailscale MagicDNS for internal communication
- No localhost assumptions for shared infrastructure
- GPU resources require special CUDA library path for faster-whisper
- **Per-Agent Worktrees (default for parallel work):** In repositories where multiple agent sessions operate concurrently, agents must run `git worktree add` on a named branch rather than sharing the primary checkout. The shared tree makes session state implicitly shared mutable state — concurrent checkouts and commits land on whatever branch the tree points at. Shared-tree use is opt-in only, for deliberate sequential handoff of uncommitted state. On session end, worktrees must be pruned or referenced in `ARTIFACTS.md` (same anti-stranding rule as stashes).
- **Verify-Origin Before State Claims:** Before reporting branch, commit, push, or PR state, verify against the live object — never session memory:
  - `git branch --show-current` before any commit/branch operation
  - `git status` / `git diff origin/<branch>` before claiming push/commit state
  - `gh pr diff <n> --name-only` + `gh pr view <n> --json commits` before describing PR contents (a claim true at commit time can be stale after rebase, merge, or concurrent activity)
- **Credential Generation Protocol (TAILSCALE-OAUTH-01):** Generate a credential only when its approved encrypted destination is ready (SOPS/age under `apps/secrets/`). Write it directly into that flow; never expose it through shell history, terminal output, clipboard staging, chat, logs, unencrypted files, pull-request diffs, CI artifacts, or generated bundles. Any credential that crosses an unapproved boundary is presumed exposed — do not deploy it; revoke or discard it before creating a replacement.
  - An outcome-only validity or revocation test may record timestamp, actor, target identity, and success/failure status — it must not retain request/response payloads, token values, secret fragments, or headers.
  - Secret scanning applies to source files, generated manifests, Helm/Kustomize render output, deployment artifacts, controller annotations (e.g. `kubectl.kubernetes.io/last-applied-configuration`), CI logs, and review bundles.

## Optimization Opportunities
- **Ollama Model Consolidation**: See ADR-015 for opportunity to consolidate llama3 (4.7GB) + gemma2:9b (5.4GB) → single Qwen2.5-3B-Instruct (~3GB), potential 7GB savings
- **Model Cache Review**: Evaluate HuggingFace cache for unused models before major service updates
- **Storage Optimization**: Regular cleanup of old model artifacts and temporary files
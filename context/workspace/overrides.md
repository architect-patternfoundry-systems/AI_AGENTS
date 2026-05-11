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
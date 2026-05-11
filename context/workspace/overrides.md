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

## Optimization Opportunities
- **Ollama Model Consolidation**: See ADR-015 for opportunity to consolidate llama3 (4.7GB) + gemma2:9b (5.4GB) → single Qwen2.5-3B-Instruct (~3GB), potential 7GB savings
- **Model Cache Review**: Evaluate HuggingFace cache for unused models before major service updates
- **Storage Optimization**: Regular cleanup of old model artifacts and temporary files
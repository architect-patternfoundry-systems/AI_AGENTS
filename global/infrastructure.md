# Global Infrastructure Governance

Cross-cutting infrastructure standards that apply to all repositories and work in this workspace.

## Standardized Connectivity Policy (ADR-012)

All operational backends and internal services MUST be resolved via authoritative Tailscale MagicDNS names.

### Core Hostnames
- **Cortex**: `cortex.tailc2cafc.ts.net`
- **Inspiron**: `ran-ubuntu-inspiron.tailc2cafc.ts.net`
- **Storage Substrate**: `storage-substrate` (DNS Alias for Cortex Node)

### NFS Exports (cortex.tailc2cafc.ts.net)

| Export path | Access | Notes |
|---|---|---|
| `/mnt/data_lake` | rw | Main storage substrate — LAN + Tailscale mesh |
| `/mnt/mediastore/seagate` | ro | Seagate USB drive — 576 Suno MP3s + archived MinIO PVCs. Requires drive to be physically connected. |

**Mount from any tailnet node:**
```bash
mount -t nfs cortex.tailc2cafc.ts.net:/mnt/mediastore/seagate /mnt/seagate
```

Cortex LAN subnet updated to `192.168.86.0/24` (was `192.168.68.0/24`). Tailscale subnet `100.64.0.0/10` covers all `.ts.net` peers.

### CUDA / faster-whisper (cortex)

CTranslate2 (used by `faster-whisper`) requires `libcublas.so.12`. The system copy lives at `/usr/local/lib/ollama/cuda_v12/`. When running any faster-whisper script from the ToneRoot venv, prepend:

```bash
LD_LIBRARY_PATH=/usr/local/lib/ollama/cuda_v12:$LD_LIBRARY_PATH .venv/bin/python3 <script>
```

`openai-whisper` (PyTorch backend) does NOT need this — it uses the cuBLAS bundled with PyTorch.

## ToneRoot-Nexus Repository Layout

All ToneRoot source now lives in `application/`. The `ToneRoot/` directory contains only the legacy Tkinter UI (pending retirement) and working artifacts.

| Path | Purpose |
|---|---|
| `application/apps/toneroot/web/backend/` | Python sidecar source (canonical) |
| `application/apps/toneroot/web/frontend/` | Next.js + Tauri shell (canonical) |
| `application/app_lib/` | Shared Python library (canonical) |
| `application/apps/toneroot/config.json` | Runtime config (secrets — gitignored, never commit) |
| `application/apps/toneroot/tools/` | Standalone ops scripts (whisper_batch.py, sync_s3_inventory.py, etc.) |
| `application/apps/toneroot/docs/` | Build guide, SDD, legacy docs |
| `ToneRoot/` | Legacy Tkinter desktop UI — do not edit; pending retirement |

### ToneRoot-Nexus Build Process

**IMPORTANT**: `npx tauri build` alone does NOT rebuild the Python sidecar. The sidecar must be rebuilt with PyInstaller first whenever any `.py` backend file changes.

Preferred: use the Makefile from `application/apps/toneroot/`:
```bash
make desktop   # sidecar + Tauri bundle
make install   # dpkg install the .deb
make audit     # corpus quality report
```

Manual sequence (from `application/apps/toneroot/web/frontend/src-tauri/`):
```bash
python3 build-sidecar.py           # Step 1: rebuild sidecar
cd .. && npx tauri build           # Step 2: bundle .deb
sudo dpkg -i src-tauri/target/release/bundle/deb/ToneRoot-Nexus_0.1.0_amd64.deb  # Step 3: install
```

The sidecar binary lands at `src-tauri/binaries/ToneRoot-Nexus-x86_64-unknown-linux-gnu`. PyInstaller uses zlib-compressed archives — searching the binary for raw strings will fail; content is only visible after decompression.

## Rules for AI Agents

1. **No Localhost Sprawl**: Do not assume services are on `localhost` if they belong to a shared infrastructure project.
2. **Authoritative Resolution**: Always verify connectivity via `pg_isready` or `ping` using canonical names before assuming failure.
3. **MagicDNS Preferred**: Prefer `.ts.net` FQDNs for cross-mesh communication to ensure consistency across nodes.
4. **Network Access**: Ensure any new service requiring data access is added to the `allow-internal-data-access` NetworkPolicy.
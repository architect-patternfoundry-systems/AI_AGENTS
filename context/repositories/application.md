# Application Repository Governance

Repository-specific guidelines and instructions for the `application` repository.

## Tauri Sidecar Build Process (ToneRoot Nexus)

**CRITICAL RULE**: Never ask the user to test changes without ensuring the sidecar binary is rebuilt when backend changes are made.

### When to Rebuild
The sidecar binary MUST be rebuilt when ANY of the following are modified:
- **Backend Python files**: `application/apps/toneroot/web/backend/*.py`
  - Especially: `ipc_server.py`, `sidecar_main.py`, `profile_manager.py`
- **IPC schema changes**: `application/app_lib/toneroot_ipc_schema.py`
- **Config templates**: `application/apps/toneroot/config.json`
- **app_lib changes**: Any files in `application/app_lib/` that are imported by the backend

### Build Process
```bash
cd application/apps/toneroot/web/frontend/src-tauri
python3 build-sidecar.py
pkill -f "ToneRoot-Nexus"
cp binaries/ToneRoot-Nexus-x86_64-unknown-linux-gnu target/debug/ToneRoot-Nexus
```

### Frontend Changes
Frontend changes (React/TypeScript) do NOT require a sidecar rebuild:
- `src/components/*.tsx`
- `src/app/*.tsx`
- `src/hooks/*.ts`
- `src/lib/*.ts`
These are hot-reloaded by Next.js during development.

### Verification
After backend changes, ALWAYS:
1. Rebuild the binary
2. Copy to `target/debug/`
3. Kill existing sidecar processes
4. Then ask the user to test

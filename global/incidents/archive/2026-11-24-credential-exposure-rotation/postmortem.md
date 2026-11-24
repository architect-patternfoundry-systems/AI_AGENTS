# Postmortem: Credential Exposure Containment (2026-11-22→24)

**Status:** Contained — both exposed credentials dead; follow-up tracks open.
**Full evidence trail:**
`infrastructure/docs/artifacts/evidence/incident-credential-exposure-2026-11/`
**Closure playbook:**
`infrastructure/docs/artifacts/runbooks/credential-exposure-incident-closure-playbook.md`

## Summary

Two still-valid credentials were leaked into CLI transcripts: PostgreSQL
role `cortex_db_admin_r16023` and MinIO root `admin` (~100 transcript
files — repeated copies, not 100 disclosures). Unauthorized use was never
established; containment proceeded anyway (exposure alone meets the
revocation threshold).

- **PG:** rotated via `CredentialRotationWorkflow` + operator-assisted
  privileged steps → successor `…_r95347`, predecessor `rolcanlogin=f`,
  zero forced terminations (pooler PAUSE drained all 9 sessions).
- **MinIO:** root rotated across all 7 secret copies + hard-cut server
  restart (sub-minute outage); 11 consumers rolled; audit log verified
  clean.
- **Hardening folded in:** `rotation_worker` and `cnpg_pooler_pgbouncer`
  lost `admin`/`set` options on the `cortex_db_admin` superuser group —
  no login-capable identity retains a `SET ROLE` path to superuser.

## Learnings for agents (start here before credential/rotation work)

### Process

1. **Bounded authorization works.** Document executor/window/identities/
   stop-conditions *before* each mutating stage; merge the record after.
   Nothing was ever "just done."
2. **Dual-valid beats revoke-then-cutover** for DB roles: create
   successor → cut consumers → drain → NOLOGIN. MinIO root has *no*
   overlap mechanism — expect a hard-cut restart.
3. **Verify state, don't assume it.** Every "established" claim in this
   incident was corrected at least once by actually checking (trust
   timeline, MAC corruption, pod identity, process parenthood).

### Technical pitfalls (all hit live)

- `psql -c` does **not** interpolate `:"var"` — use stdin-fed psql.
- `superuser-assist.sh` defaults `PG_POD=postgres-2` (the *replica*) —
  resolve the primary at exec time via `cnpg.io/instanceRole`.
- **Worker restart → workflow start = dispatch race**: a task can land on
  a draining pod and wedge to `schedule_to_close`. Verify a settled
  worker before starting.
- In-pod `sops -d` needs `SOPS_AGE_KEY_FILE=/etc/sops/age-key.txt`
  (env var absent); worker rootfs is read-only — stage to `/workspace`.
- sops **MAC mismatch** = file edited post-seal (Flux tolerates it);
  `--ignore-mac` to read, `sops -e` to repair.
- `GRANT … WITH ADMIN FALSE, SET FALSE` — *not* `OPTION FALSE`.
- ConfigMap/envFrom changes need pod restart; restart-annotations
  revert on next Flux apply — verify env on the *live* pod.
- `ss -tln` on the host does **not** show pod-netns listeners; a
  containerd-shim parent means "pod container," not rogue process.
- CronJobs/consumers holding rotated creds need pod restarts except
  cron (reads secret at next scheduled run).

### Security findings carried forward (open tracks)

- **PgBouncer `auth_type=trust`** — longstanding (file created
  2026-07-17, Aug-13 changes reverted). Console/data access reduces to
  claiming a `userlist`-listed username; no password check. Undermines
  credential integrity on the pooled path. Stalled SCRAM plan exists.
- **MinIO root still shared** — scoped-user migration deferred; the
  per-app policy pattern already exists (`cts-backend-s3`, etc.).
- **No `pg_stat_statements`** — privilege *use* isn't auditable;
  non-use of SET/GRANT paths can't be history-proven.
- Stale surface: `rolcanlogin=f` predecessor roles, scaled-0
  deployments, `.new`/`.tmp` secret files.

### Tooling created this incident

- `infrastructure/scripts/update-mc-root-aliases.py` — post-rotation
  `~/.mc/config.json` updater (dry-run mode, endpoint allowlist,
  skips ambiguous hosts).
- Receipt-based approval gate (`rotation-receipt/v1`, ed25519) —
  approver `devin-operator`, fp `5e8e2349…2e9928`.

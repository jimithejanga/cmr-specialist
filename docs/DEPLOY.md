# DEPLOY — ship CMR Specialist to any VM (finished-product path)

One repo, one script, one VM. No laptop dependencies.

## 1. Requirements (VM side)

- Ubuntu 22.04, 2 vCPU / 4 GB RAM / 40 GB disk (see prior notes for $0–$7 options)
- This repo cloned: `git clone https://github.com/jimithejanga/cmr-specialist.git`
- Root/sudo for the Docker install step only

## 2. Install (one command)

```bash
cd cmr-specialist
sudo -E ./deploy/install.sh
```

Optional knobs (env, all have safe defaults):

| Var | Meaning | Default |
|---|---|---|
| `ADMIN_USER` / `ADMIN_PASSWORD` | first login (admin) | `Baba` / random printed once |
| `INFERENCE_API_KEY` + `INFERENCE_PROVIDER` | real model (`openrouter`/…); empty = built-in mock | mock |
| `TUNNEL_TOKEN` | Cloudflare named-tunnel token (enables `tunnel` service) | empty (localhost-only) |
| `SKIP_DOCKER=1` | docker already installed | 0 |
| `SKIP_BOOT=1` | write `.env` only | 0 |

The script: installs Docker → writes `.env` (`chmod 600`, `STRICT_AUTH=1`,
random `POSTGRES_PASSWORD`/`HARNESS_API_KEY`/`TOOL_MODULE_TOKEN`) → builds →
starts `web + worker + db + backup + registry` → waits for both health
endpoints → creates the first admin → proves backup **and** restore →
prints URLs + credentials.

Re-runs are safe: existing `.env` and existing admin are never overwritten.

## 3. What you get

- `web :8080` — operator console `/`, admin `/admin`, API `/docs`, health `/health`
- `registry :8081` — tables/links/feed at `/console/` (own Postgres DB `cmr_registry`)
- `worker` — durable queue, heartbeats so `/health worker_heartbeat` is live
- `backup` — nightly `pg_dump`, 14-day keep; `docker/restore.sh` proves restores
- Postgres is **never published** — reachable only inside compose
- All services `restart: unless-stopped` (survive reboot)

## 4. Remote access (nothing is public by default)

- **Cloudflare named tunnel:** `cloudflared tunnel login/create/route`, put the
  token in `.env` as `TUNNEL_TOKEN`, re-run:
  `docker compose -f docker/docker-compose.yml --profile tunnel up -d`
- **Tailscale:** install on VM + devices, `tailscale up`, `tailscale serve 8080`
  (and `8081` for the registry console)

## 5. Daily ops

- Morning: `/admin/worker.html` — heartbeat fresh, queue near zero
- Weekly: fresh file in `pg_backups` volume + offsite copy, disk use
- Update: `git pull && docker compose -f docker/docker-compose.yml up -d --build`
- Rollback: `git checkout <prior-tag> && ... up -d --build` (tag releases: `git tag vX.Y`)
- Never delete volumes to "fix" things — restart containers

## 6. Validated matrix (2026-10-12, pre-release check)

- `pytest tests/` green (SQLite + mock)
- Full product path on **Postgres 16**: health, admin bootstrap, session login
  (both services), registry tables/browse/links/feed + synthetic insert,
  knowledge-query case flow, worker heartbeat live — all `200`
- Backup + restore-proof executed inside the `postgres:16-alpine` image
  (same image the compose `backup` service uses)
- Fixed for Postgres: `active_certificates` view (`DROP+CREATE`, no `IF NOT EXISTS`)
- Note: first `docker build` downloads ~100 MB of wheels — needs decent network
  (slow links take 10+ min once, then cached)

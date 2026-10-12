# Office-PC Pilot — $0 runbook (this machine hosts, remote device tests)

Target: this computer runs everything (`web + worker + db + backup + registry`
via `docker/docker-compose.yml`), no open ports. A remote device (phone/laptop)
tests over Cloudflare Tunnel or Tailscale.

## 1. Prepare this host (once)

```bash
cp .env.example .env && chmod 600 .env
# edit .env: fresh POSTGRES_PASSWORD, HARNESS_API_KEY, TOOL_MODULE_TOKEN,
# INFERENCE_API_KEY, STRICT_AUTH=1, REGISTRY_OPERATORS=<you>
docker compose -f docker/docker-compose.yml up -d --build
curl -s http://127.0.0.1:8080/health   # {"status":"ok",...}
```

Containers auto-restart (`unless-stopped`). Postgres is NOT published —
only `web :8080` + `registry :8081` bind localhost.

## 2. Expose to the remote device (pick ONE)

**A) Cloudflare Tunnel (recommended if you have a domain):**
```bash
cloudflared tunnel login
cloudflared tunnel create cmr-office
cloudflared tunnel route dns cmr-office cmr.youroffice.com
# paste token into .env as TUNNEL_TOKEN, then:
docker compose -f docker/docker-compose.yml --profile tunnel up -d --build
# remote device opens https://cmr.youroffice.com
```

**B) Tailscale (no domain, fastest):**
```bash
# both machines: install tailscale, same account, `tailscale up`
tailscale serve 8080          # on this host (and `tailscale serve 8081` for registry console)
# remote device opens the tailnet URL shown by `tailscale serve status`
```

## 3. First admin + lock check

On THIS host only (never over the tunnel):
create first user → auto-admin → sign in at `/admin`, confirm ADMIN badge,
create tester login. With `STRICT_AUTH=1` the stack refuses default secrets
at startup (`configs/settings.py:assert_pilot_secrets`).

## 4. Remote-device test script (~10 min)

1. `GET /health` → ok.
2. `/` operator console: sign in, new case (“How do I renew my CMR certificate?”),
   follow-up on same case, queue `payment_reconciliation`, approve/reject.
3. `/admin/worker.html`: heartbeat fresh, queue drains to zero.
4. `:8081/console` (via second tunnel/serve): tables browse, one links biography, feed shows agent writes.
5. Note any `fallback` badge — re-check that result before acting.

## 5. Backup proof (before real cases)

```bash
docker compose -f docker/docker-compose.yml exec backup /backup/nightly_backup.sh
docker compose -f docker/docker-compose.yml exec backup /backup/restore-proof.sh
# expect: restore proof OK + countable cases table
```

## 6. Daily

Morning 30s: Worker page heartbeat + queue age. Weekly 10min: fresh backup +
offsite copy timestamp + disk use. Rollback = restart previous image tag.
Never delete volumes to “fix” things — restart containers.

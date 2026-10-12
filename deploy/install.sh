#!/bin/bash
# CMR Specialist — one-shot product installer (Ubuntu 22.04 VM or any Docker host).
#
# Usage (from the repo root, after `git clone <url> && cd cmr-specialist`):
#   sudo -E ./deploy/install.sh
# Options via environment (all optional):
#   ADMIN_USER        first login name            (default: Baba)
#   ADMIN_PASSWORD    first login password        (default: random, printed at end)
#   INFERENCE_API_KEY OpenRouter/Gemini key       (default: empty -> mock provider)
#   INFERENCE_PROVIDER mock|openrouter|gemini|http (default: mock, or openrouter if key given)
#   TUNNEL_TOKEN      Cloudflare tunnel token    (default: empty -> localhost-only)
#   SKIP_DOCKER=1     skip apt/docker install    (docker already present)
#   SKIP_BOOT=1       only write .env, don't start
#
# Result: Postgres-backed web + worker + backup + registry, STRICT_AUTH=1,
# fresh secrets, first admin created, backup proven. Re-runnable: existing
# .env and existing admin are never overwritten.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

say() { printf '\n==> %s\n' "$*"; }
rand() { openssl rand -hex 24; }

# ── 1. Docker ──────────────────────────────────────────────────────────────
if [ "${SKIP_DOCKER:-0}" = "1" ]; then
  say "SKIP_DOCKER=1, keeping existing docker"
else
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    say "docker already present: $(docker --version | head -1)"
  else
    say "installing docker + compose + basics"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      docker.io docker-compose-plugin git curl openssl ca-certificates
    systemctl enable --now docker 2>/dev/null || service docker start 2>/dev/null || true
  fi
fi
command -v docker >/dev/null || { echo "docker install failed"; exit 1; }

# ── 2. .env with fresh secrets (never overwrite) ───────────────────────────
if [ -f .env ]; then
  say ".env exists — keeping it (delete to regenerate)"
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
else
  say "writing fresh .env (STRICT_AUTH=1, random secrets)"
  cp .env.example .env
  chmod 600 .env
  POSTGRES_PASSWORD="$(rand)"; HARNESS_API_KEY="$(rand)"; TOOL_MODULE_TOKEN="$(rand)"
  sed -i "s|CHANGE-ME-db-password|$POSTGRES_PASSWORD|" .env
  sed -i "s|CHANGE-ME-long-random-string|$HARNESS_API_KEY|" .env
  sed -i "s|CHANGE-ME-other-long-random-string|$TOOL_MODULE_TOKEN|" .env
  if [ -n "${INFERENCE_API_KEY:-}" ]; then
    sed -i "s|^INFERENCE_PROVIDER=mock|INFERENCE_PROVIDER=${INFERENCE_PROVIDER:-openrouter}|" .env
    sed -i "s|^# INFERENCE_API_KEY=.*|INFERENCE_API_KEY=${INFERENCE_API_KEY}|" .env
    grep -q "^INFERENCE_API_KEY=" .env || echo "INFERENCE_API_KEY=${INFERENCE_API_KEY}" >> .env
  fi
  if [ -n "${TUNNEL_TOKEN:-}" ]; then
    sed -i "s|^# TUNNEL_TOKEN=.*|TUNNEL_TOKEN=${TUNNEL_TOKEN}|" .env
    grep -q "^TUNNEL_TOKEN=" .env || echo "TUNNEL_TOKEN=${TUNNEL_TOKEN}" >> .env
  fi
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi

ADMIN_USER="${ADMIN_USER:-Baba}"
ADMIN_GENERATED=0
if [ -z "${ADMIN_PASSWORD:-}" ]; then
  ADMIN_PASSWORD="$(openssl rand -hex 12)"
  ADMIN_GENERATED=1
fi
PROFILE_ARGS=""
[ -n "${TUNNEL_TOKEN:-}" ] && PROFILE_ARGS="--profile tunnel"

# ── 3. Boot ────────────────────────────────────────────────────────────────
if [ "${SKIP_BOOT:-0}" = "1" ]; then
  say "SKIP_BOOT=1 — .env ready, stack not started"
else
  say "building + starting (this takes a few minutes first time)"
  # shellcheck disable=SC2086
  docker compose -f docker/docker-compose.yml $PROFILE_ARGS up -d --build
  say "waiting for web :8080"
  for i in $(seq 1 45); do
    if curl -sf -m 3 http://127.0.0.1:8080/health >/dev/null 2>&1; then break; fi
    sleep 4
    [ "$i" = "45" ] && { echo "web never became healthy"; docker compose -f docker/docker-compose.yml logs --tail=30 web; exit 1; }
  done
  say "waiting for registry :8081"
  for i in $(seq 1 30); do
    if curl -sf -m 3 http://127.0.0.1:8081/health >/dev/null 2>&1; then break; fi
    sleep 4
    [ "$i" = "30" ] && { echo "registry never became healthy"; docker compose -f docker/docker-compose.yml logs --tail=30 registry; exit 1; }
  done
  curl -s http://127.0.0.1:8080/health; echo
  curl -s http://127.0.0.1:8081/health; echo
fi

# ── 4. First admin (bootstrap open only when zero users) ───────────────────
if [ "${SKIP_BOOT:-0}" = "1" ]; then
  say "SKIP_BOOT=1 — create the admin after first boot (step 5 in DEPLOY.md)"
else
  say "creating first admin '$ADMIN_USER' (skipped if users exist)"
  CREATE_OUT=$(curl -s -m 10 -X POST http://127.0.0.1:8080/auth/users \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASSWORD\",\"is_admin\":true}" || true)
  echo "$CREATE_OUT"
  LOGIN_CODE=$(curl -s -m 10 -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8080/auth/login \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASSWORD}")
  if [ "$LOGIN_CODE" = "200" ]; then
    say "admin login verified (HTTP 200)"
  else
    echo "NOTE: login as $ADMIN_USER returned HTTP $LOGIN_CODE."
    echo "If users already existed, sign in with the original password instead."
  fi
  # ── 5. Backup proof ────────────────────────────────────────────────────
  say "proving backup + restore"
  docker compose -f docker/docker-compose.yml exec -T backup /backup/nightly_backup.sh
  docker compose -f docker/docker-compose.yml exec -T backup /backup/restore-proof.sh
fi

# ── 6. Summary ─────────────────────────────────────────────────────────────
cat <<SUMMARY

================ CMR Specialist is up ================
Operator console : http://<this-host>:8080/  (API docs .../docs, health .../health)
Admin site       : http://<this-host>:8080/admin
Registry console : http://<this-host>:8081/console/
API key          : see .env HARNESS_API_KEY (chmod 600, never share the file)
Admin login      : user '$ADMIN_USER'${ADMIN_GENERATED:+ / password '$ADMIN_PASSWORD' (SAVE THIS — shown only here)}
DB               : Postgres (cmr + cmr_registry), nightly dumps, 14-day keep
Remote access    : no ports are public. Add TUNNEL_TOKEN to .env and
                   re-run with --profile tunnel, or use Tailscale.
======================================================
SUMMARY

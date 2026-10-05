#!/usr/bin/env bash
# One-time setup of Mu'een's API on a fresh Ubuntu 24.04 server (Hetzner CX33).
# Run as root on the server:
#     curl -fsSL <raw url of this file> -o setup.sh   (or scp it)  &&  bash setup.sh
# It asks for the secrets interactively, so nothing secret is stored in git or in the shell history.
set -euo pipefail

REPO=${REPO:-https://github.com/tgfdru/hikmah-dev.git}
BRANCH=${BRANCH:-nader/agent}
APP=/opt/mueen

echo "== 1/7 system packages, firewall, swap"
apt-get update -qq
apt-get install -y -qq git curl ufw openssl ca-certificates >/dev/null
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw --force enable >/dev/null
if ! swapon --show | grep -q /swapfile; then   # the embedding models need headroom while building
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== 2/7 Docker"
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh >/dev/null

echo "== 3/7 code ($BRANCH)"
read -rsp "GitHub read-only token for the private repo: " GH; echo
AUTH="Authorization: Basic $(printf 'x-access-token:%s' "$GH" | base64 -w0)"
if [ -d "$APP/.git" ]; then
  git -C "$APP" -c http.extraHeader="$AUTH" pull -q
else
  git -c http.extraHeader="$AUTH" clone -q -b "$BRANCH" "$REPO" "$APP"
fi
cd "$APP"

echo "== 4/7 secrets (.env, never committed)"
if [ ! -f .env ]; then
  read -rsp "Gemini API key (AI Studio): " GEMINI; echo
  read -rsp "OpenCode Zen key (independent judge; Enter to skip): " ZEN; echo
  read -rp  "Service end date YYYY-MM-DD (Enter = none): " UNTIL
  SITE_KEY=$(openssl rand -hex 24)
  cat > .env <<ENV
RETRIEVER=hybrid
AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
AI_API_KEY=$GEMINI
AI_MODEL=gemini-3.5-flash-lite
AI_MODEL_ANALYZE=gemini-3.1-flash-lite
AI_MODEL_ROUTE=gemini-3.1-flash-lite
AI_MODEL_GENERATE=gemini-3.8-flash
AI_MODEL_FALLBACK=gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite
VERIFY_LLM_JUDGE=$([ -n "$ZEN" ] && echo 1 || echo 0)
AI_JUDGE_BASE_URL=https://opencode.ai/zen/v1
AI_JUDGE_API_KEY=$ZEN
AI_MODEL_JUDGE=gpt-5.4-nano
MUEEN_API_KEYS=$SITE_KEY
MUEEN_SERVICE_UNTIL=$UNTIL
ENV
  chmod 600 .env
  echo ">> API key for the site's server (X-API-Key): $SITE_KEY   <- save it, it is shown once"
fi

echo "== 5/7 domain"
if [ ! -f deploy/.env.deploy ]; then
  IP=$(curl -fsS https://api.ipify.org)
  read -rp "Domain for HTTPS (Enter = $IP.sslip.io): " DOM
  echo "DOMAIN=${DOM:-$IP.sslip.io}" > deploy/.env.deploy
fi

C="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml"
echo "== 6/7 knowledge base (downloads sources, builds store + index; 20-60 min the first time)"
$C up -d qdrant
$C --profile build run --rm kb-build

echo "== 7/7 API + HTTPS"
$C up -d --build api caddy
. deploy/.env.deploy
for i in $(seq 1 60); do curl -fsS "https://$DOMAIN/health" >/dev/null 2>&1 && break; sleep 5; done
curl -fsS "https://$DOMAIN/health" && echo && echo "Done: https://$DOMAIN"

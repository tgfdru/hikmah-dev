#!/usr/bin/env bash
# Pull new code and restart. REBUILD_KB=1 also rebuilds the knowledge base (after new sources).
#     cd /opt/mueen && bash deploy/update.sh            |  REBUILD_KB=1 bash deploy/update.sh
set -euo pipefail
cd /opt/mueen
read -rsp "GitHub read-only token: " GH; echo
git -c http.extraHeader="Authorization: Basic $(printf 'x-access-token:%s' "$GH" | base64 -w0)" pull -q
C="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml"
if [ "${REBUILD_KB:-0}" = 1 ]; then $C --profile build run --rm --build kb-build; fi
$C up -d --build api caddy
. deploy/.env.deploy
sleep 20; curl -fsS "https://$DOMAIN/health"; echo

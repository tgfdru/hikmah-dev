#!/usr/bin/env bash
# Owner's kill switch: stop answering immediately (data and index are kept).
# Start again with: docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d api caddy
cd /opt/mueen && docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml stop api caddy

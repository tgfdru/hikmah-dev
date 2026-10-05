# Deploying the API (Hetzner CX33, Ubuntu 24.04)

Owner: Nader. The service runs on the owner's server with the owner's model keys; the
site (sheykak.com) calls it from its own server with an `X-API-Key` (docs/API_INTEGRATION.md).

## First time (≈ 30–60 min, mostly the knowledge-base build)

1. Create the server: Hetzner Cloud → CX33, Ubuntu 24.04, your SSH key.
2. Copy the script and run it as root:
   ```bash
   scp deploy/setup.sh root@<IP>:/root/  &&  ssh root@<IP> 'bash /root/setup.sh'
   ```
   It asks for: a **read-only GitHub token** (fine-grained, Contents: read, this repo only),
   the **Gemini key**, the **OpenCode Zen key** (independent judge; optional), an optional
   **service end date**, and a domain (default `<IP>.sslip.io`, HTTPS via Let's Encrypt).
3. It prints the **site API key** once — give it privately to the site team.
4. Check: `curl https://<domain>/health`.

What it sets up: firewall (22/80/443), 4 GB swap, Docker, the repo in `/opt/mueen`,
`.env` (mode 600, never committed), Qdrant, the knowledge base (`kb-build`), the API and
Caddy (HTTPS) — `deploy/docker-compose.prod.yml`.

## Later

| Task | Command (on the server) |
|---|---|
| New code | `cd /opt/mueen && bash deploy/update.sh` |
| New sources (rebuild index) | `REBUILD_KB=1 bash deploy/update.sh` |
| Stop the service (owner's switch) | `bash deploy/stop.sh` |
| Logs | `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs -f api` |
| Rotate the site key | edit `MUEEN_API_KEYS` in `/opt/mueen/.env`, then `update.sh` |
| End date | `MUEEN_SERVICE_UNTIL=YYYY-MM-DD` in `.env` → `/suggest` answers 403 after it |

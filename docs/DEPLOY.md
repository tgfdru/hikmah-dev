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

## Alternative: an existing Dokploy server

`deploy/docker-compose.dokploy.yml` runs the same stack as a Dokploy **Compose** service
(Qdrant + one-shot `kb-build` + API; Traefik in front, no host ports).

1. Dokploy → Project → **Create Service → Compose**.
2. Provider **GitHub**: repo `tgfdru/hikmah-dev`, branch `nader/agent`,
   Compose path `./deploy/docker-compose.dokploy.yml`.
3. **Environment** tab (secrets live only here):
   ```
   AI_API_KEY=<Gemini key>
   AI_JUDGE_API_KEY=<OpenCode Zen key>
   MUEEN_API_KEYS=<site key: openssl rand -hex 24>
   MUEEN_SERVICE_UNTIL=          # optional YYYY-MM-DD
   ```
   Model names have defaults in the compose file and can be overridden here.
4. **Domains** tab: service `api`, port `8000`, HTTPS on.
5. **Deploy**. First build ≈ 10–20 min (images + models); later deploys ≈ 2–5 min.
6. Check `https://<domain>/health`.

Needs on the server: ≈ 6 GB free RAM and ≈ 20 GB disk for this stack.

Ownership note: on a server someone else administers, the owner's control is the model keys
(revoking `AI_API_KEY`/`AI_JUDGE_API_KEY` stops the service), `MUEEN_SERVICE_UNTIL`, and the
site key — not the server itself. Keep the keys in the owner's accounts.

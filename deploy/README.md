# Deploying ClosureIQ to Akamai Cloud

The app runs in Docker Compose on one Linode VM (Ubuntu 24.04, Dallas, 4 GB). Public address: `http://173.255.199.71`. Owner: Suraj.

## Deploy

From the repo root on your laptop:

```
./deploy/deploy.sh
```

It refuses to run with uncommitted changes, pulls `main`, copies the checkout to the VM, rebuilds the containers and checks `/api/health`. The first run creates `/opt/closureiq/.env` from `.env.example`. Edit it on the VM (`nano /opt/closureiq/.env`), add the real keys there, then rerun the script. Keys exist only on the VM and on your own laptop.

## What runs

- `api`: the FastAPI backend on port 8000, inside the Docker network only.
- `web`: Caddy on ports 80 and 443. It serves the built React app and forwards `/api/*` to `api`, with streaming turned on for the live-update events.
- The database file lives on the VM at `/opt/closureiq/data/closureiq.db` and survives restarts. Back it up before the final demo.

## What the team's code must do for this to work

| Who | Rule |
|---|---|
| Badri | Put the Python dependencies in `requirements.txt` at the repo root. Read the database path from the `DB_PATH` environment variable. Serve `GET /api/health` |
| Kavya | `npm run build` must write `frontend/dist`. Commit `package-lock.json`. Call the API with relative paths like `/api/...`, never `http://localhost:8000` |
| Samanth | Read the model provider and keys from environment variables, as in `.env.example` |
| Everyone | No secrets in code. No absolute local paths |

## Useful commands on the VM

```
ssh root@173.255.199.71
cd /opt/closureiq
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs --tail 50 api
docker compose -f deploy/docker-compose.yml restart
```

## Notes

- HTTPS needs a domain name. Until we have one, the site is plain HTTP.
- Outbound email ports (SMTP) are restricted on this VM. Real email must use the provider's HTTPS API.
- The VM bills against the team's Akamai credit. Do not create other resources.
- Before the first real deploy, remove the placeholder page that uses port 80: `docker rm -f hello` (the script also does this).

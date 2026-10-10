#!/usr/bin/env bash
# One-command deploy. Run it from the repo root on your laptop: ./deploy/deploy.sh
# It copies your up-to-date checkout to the VM, rebuilds the containers and checks /api/health.
set -euo pipefail

HOST="${DEPLOY_HOST:-root@173.255.199.71}"
DIR=/opt/closureiq

if [ -n "$(git status --porcelain)" ]; then
  echo "Uncommitted changes. Commit or stash first, so the VM matches the repo." >&2
  exit 1
fi
git pull --ff-only

ssh "$HOST" "mkdir -p $DIR/data"
rsync -az --delete \
  --exclude .git --exclude node_modules --exclude data --exclude .env \
  ./ "$HOST:$DIR/"

ssh "$HOST" "cd $DIR \
  && { [ -f .env ] || { cp .env.example .env && echo 'Created .env from .env.example: edit it on the VM and rerun.'; }; } \
  && docker rm -f hello >/dev/null 2>&1 || true"

ssh "$HOST" "cd $DIR && docker compose -f deploy/docker-compose.yml up -d --build"

echo "Checking health..."
for i in $(seq 1 20); do
  if ssh "$HOST" "curl -fsS http://localhost/api/health" >/dev/null 2>&1; then
    echo "Deployed. http://${HOST#*@}"
    exit 0
  fi
  sleep 3
done
echo "Deployed, but /api/health did not answer. Check: ssh $HOST 'cd $DIR && docker compose -f deploy/docker-compose.yml logs --tail 50'" >&2
exit 1

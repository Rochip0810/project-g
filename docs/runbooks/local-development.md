# Project G Local Development Runbook

## Start Project G

~~~bash
cd ~/projects/project-g

docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  up -d
~~~

## Check service status

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  ps --all
~~~

Expected state:

- API: running and healthy
- PostgreSQL: running and healthy
- Redis: running and healthy
- Migration: exited with code 0
- Worker: running
- Scheduler: running

## Check API readiness

~~~bash
curl -fsS \
  http://127.0.0.1:8000/api/v1/health/readiness \
  | uv run python -m json.tool
~~~

## View logs

All services:

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  logs --tail=200
~~~

Specific services:

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  logs --tail=200 api worker scheduler
~~~

## Stop Project G safely

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  down
~~~

This preserves PostgreSQL and Redis volumes.

## Restart Project G

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  down

docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  up -d
~~~

## Rebuild after code or dependency changes

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  build

docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  up -d
~~~

## Run database migrations manually

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  run --rm migrate
~~~

## Check the current Alembic revision

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version;"'
~~~

## Run the complete Phase 0 acceptance test

~~~bash
./scripts/phase0-acceptance.sh
~~~

## Recovery when a service fails

Check status and logs first:

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  ps --all

docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  logs --tail=300
~~~

Restart without deleting data:

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  down

docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  up -d
~~~

## Destructive reset

Only use this when all local PostgreSQL and Redis data may be deleted.

~~~bash
docker compose \
  --env-file .env \
  -f docker/compose.yaml \
  down --volumes --remove-orphans
~~~

Never use `down --volumes` during normal shutdown or persistence tests.

## Git rollback

Revert a merged Pull Request:

~~~bash
git switch main
git pull --ff-only origin main
git revert <commit-sha>
git push origin main
~~~

Do not rewrite shared main-branch history.

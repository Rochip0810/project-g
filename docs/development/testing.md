# Project G Testing Guide

## Test categories

### Unit tests

Fast and isolated tests that do not require external services.

~~~bash
./scripts/test-unit.sh
~~~

### Integration tests

Tests combining multiple Project G components with temporary local resources.

~~~bash
./scripts/test-integration.sh
~~~

### Docker smoke tests

Tests the running local Docker Compose environment.

Start the environment first:

~~~bash
docker compose --env-file .env -f docker/compose.yaml up -d
~~~

Run the smoke tests:

~~~bash
./scripts/test-docker.sh
~~~

### Standard local quality check

Runs Ruff, mypy, Unit Tests, and Integration Tests. Docker tests are excluded.

~~~bash
./scripts/test-all.sh
~~~

## Direct pytest commands

~~~bash
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m docker --run-docker
uv run pytest -m "not docker"
~~~

## Safety rules

- Never use production credentials in tests.
- Never connect tests to production PostgreSQL or Redis.
- Docker tests target localhost only.
- Publishing must remain disabled during all tests.
- Temporary database files must be created through pytest fixtures.

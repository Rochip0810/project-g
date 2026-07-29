# Project G Phase 0 Acceptance Checklist

## Repository and quality

- [x] Main branch is synchronized with origin/main
- [x] Working tree is clean
- [x] Ruff formatting passes
- [x] Ruff lint passes
- [x] mypy passes
- [x] Unit Tests pass
- [x] Integration Tests pass
- [x] Docker Smoke Tests pass
- [x] GitHub Actions Quality checks pass
- [x] GitHub Actions Docker integration passes

## Runtime platform

- [x] Docker image builds
- [x] Docker Compose configuration is valid
- [x] PostgreSQL is healthy
- [x] Redis is healthy
- [x] Migration exits with code 0
- [x] Alembic revision is 0001_baseline
- [x] API liveness returns HTTP 200
- [x] API readiness returns HTTP 200
- [x] Database readiness is true
- [x] Redis readiness is true
- [x] Migration readiness is true
- [x] Worker is running
- [x] Scheduler is running
- [x] Scheduler heartbeat is processed by the Worker
- [x] PostgreSQL data survives container recreation

## Security and safety

- [x] Publishing is disabled
- [x] `.env` is not tracked by Git
- [x] No credential files are tracked
- [x] API is bound only to 127.0.0.1
- [x] PostgreSQL is not exposed to the host
- [x] Redis is not exposed to the host
- [x] Application containers use a non-root user
- [x] Production credentials are not required
- [x] Normal shutdown does not delete data volumes

## Operations

- [x] Startup procedure is documented
- [x] Shutdown procedure is documented
- [x] Recovery procedure is documented
- [x] Migration procedure is documented
- [x] Rollback procedure is documented
- [x] Destructive reset is clearly marked

## Final decision

- [x] Phase 0 completion report is approved
- [x] Phase 1 development is authorized

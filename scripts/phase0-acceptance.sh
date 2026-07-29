#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="${COMPOSE_FILE:-docker/compose.yaml}"
ENV_FILE="${ENV_FILE:-.env}"
BASE_URL="${PROJECT_G_DOCKER_BASE_URL:-http://127.0.0.1:8000}"
REQUIRE_CLEAN_REPOSITORY="${REQUIRE_CLEAN_REPOSITORY:-true}"
LOG_FILE="${PHASE0_LOG_FILE:-logs/phase0-acceptance.log}"

mkdir -p "$(dirname "${LOG_FILE}")"
: > "${LOG_FILE}"
exec > >(tee -a "${LOG_FILE}") 2>&1

compose() {
    docker compose \
        --env-file "${ENV_FILE}" \
        -f "${COMPOSE_FILE}" \
        "$@"
}

pass() {
    printf 'PASS: %s\n' "$1"
}

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

on_error() {
    local line_number="$1"

    printf '\nAcceptance test failed near line %s.\n' "${line_number}" >&2
    printf 'Docker status and recent logs follow.\n\n' >&2

    compose ps --all || true
    compose logs --no-color --tail=200 || true
}

trap 'on_error "${LINENO}"' ERR

require_command() {
    local command_name="$1"

    if ! command -v "${command_name}" >/dev/null 2>&1; then
        fail "Required command is missing: ${command_name}"
    fi
}

wait_for_readiness() {
    local response_file
    response_file="$(mktemp)"

    for attempt in $(seq 1 30); do
        printf 'Readiness attempt %s/30\n' "${attempt}"

        if curl \
            --fail \
            --silent \
            --show-error \
            "${BASE_URL}/api/v1/health/readiness" \
            > "${response_file}"
        then
            if uv run python -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    payload = json.load(file)

expected_checks = {
    "database": True,
    "redis": True,
    "migrations": True,
}

if payload.get("status") != "ready":
    raise SystemExit(f"Unexpected readiness status: {payload}")

if payload.get("checks") != expected_checks:
    raise SystemExit(f"Unexpected dependency checks: {payload}")
' "${response_file}"
            then
                cat "${response_file}"
                rm -f "${response_file}"
                pass "API readiness"
                return 0
            fi
        fi

        sleep 5
    done

    rm -f "${response_file}"
    fail "API did not become ready"
}

get_database_revision() {
    compose exec -T db sh -c \
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version;"' \
        | tr -d '[:space:]'
}

verify_running_services() {
    local running_services
    running_services="$(compose ps --status running --services)"

    printf '%s\n' "${running_services}"

    for service in api db queue worker scheduler; do
        if ! grep -qx "${service}" <<< "${running_services}"; then
            fail "Required service is not running: ${service}"
        fi
    done

    pass "Required Docker services are running"
}

verify_migration() {
    local container_id
    local exit_code
    local revision

    container_id="$(compose ps --all -q migrate)"

    if [[ -z "${container_id}" ]]; then
        fail "Migration container was not found"
    fi

    exit_code="$(
        docker inspect \
            --format '{{.State.ExitCode}}' \
            "${container_id}"
    )"

    [[ "${exit_code}" == "0" ]] \
        || fail "Migration exit code was ${exit_code}"

    revision="$(get_database_revision)"

    [[ "${revision}" == "0001_baseline" ]] \
        || fail "Unexpected Alembic revision: ${revision}"

    pass "Migration completed at 0001_baseline"
}

verify_port_exposure() {
    local api_container_id
    local database_container_id
    local redis_container_id
    local api_ports
    local database_ports
    local redis_ports

    api_container_id="$(compose ps -q api)"
    database_container_id="$(compose ps -q db)"
    redis_container_id="$(compose ps -q queue)"

    [[ -n "${api_container_id}" ]] \
        || fail "API container was not found"

    [[ -n "${database_container_id}" ]] \
        || fail "PostgreSQL container was not found"

    [[ -n "${redis_container_id}" ]] \
        || fail "Redis container was not found"

    api_ports="$(
        docker inspect \
            --format '{{json .NetworkSettings.Ports}}' \
            "${api_container_id}"
    )"

    database_ports="$(
        docker inspect \
            --format '{{json .NetworkSettings.Ports}}' \
            "${database_container_id}"
    )"

    redis_ports="$(
        docker inspect \
            --format '{{json .NetworkSettings.Ports}}' \
            "${redis_container_id}"
    )"

    uv run python - \
        "${api_ports}" \
        "${database_ports}" \
        "${redis_ports}" <<'PY_PORTS'
import json
import sys

api_ports = json.loads(sys.argv[1])
database_ports = json.loads(sys.argv[2])
redis_ports = json.loads(sys.argv[3])

api_bindings = api_ports.get("8000/tcp")
expected_api_bindings = [
    {
        "HostIp": "127.0.0.1",
        "HostPort": "8000",
    }
]

if api_bindings != expected_api_bindings:
    raise SystemExit(
        f"Unexpected API host binding: {api_bindings}"
    )

database_bindings = database_ports.get("5432/tcp")

if database_bindings not in (None, []):
    raise SystemExit(
        f"PostgreSQL is exposed to the host: "
        f"{database_bindings}"
    )

redis_bindings = redis_ports.get("6379/tcp")

if redis_bindings not in (None, []):
    raise SystemExit(
        f"Redis is exposed to the host: {redis_bindings}"
    )
PY_PORTS

    pass "Host port exposure is safe"
}

verify_scheduler_worker_flow() {
    local combined_logs=""

    for attempt in $(seq 1 20); do
        combined_logs="$(
            compose logs \
                --no-color \
                --tail=300 \
                scheduler worker \
                2>&1 || true
        )"

        if grep -q "scheduler_iteration_completed" \
            <<< "${combined_logs}" \
            && grep -Eq \
                "system_heartbeat|Job OK|Successfully completed" \
                <<< "${combined_logs}"
        then
            pass "Scheduler and Worker heartbeat flow"
            return 0
        fi

        printf 'Waiting for Scheduler and Worker evidence: %s/20\n' \
            "${attempt}"
        sleep 3
    done

    printf '%s\n' "${combined_logs}"
    fail "Scheduler and Worker heartbeat evidence was not found"
}

printf '========================================\n'
printf 'Project G Phase 0 Acceptance Test\n'
printf '========================================\n'

require_command git
require_command uv
require_command docker
require_command curl

[[ -f "${ENV_FILE}" ]] \
    || fail "${ENV_FILE} does not exist"

grep -qx 'PUBLISHING_ENABLED=false' "${ENV_FILE}" \
    || fail "Publishing is not explicitly disabled"

pass "Publishing is disabled"

if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    fail ".env is tracked by Git"
fi

pass ".env is not tracked by Git"

tracked_sensitive_files="$(
    git ls-files \
        | grep -E \
            '(^|/)\.env($|\.)|credentials.*\.json$|tokens?\.json$|\.pem$|\.key$' \
        | grep -vE '(^|/)\.env\.example$' \
        || true
)"

[[ -z "${tracked_sensitive_files}" ]] \
    || fail "Potential sensitive files are tracked: ${tracked_sensitive_files}"

pass "No obvious credential files are tracked"

if [[ "${REQUIRE_CLEAN_REPOSITORY}" == "true" ]]; then
    [[ -z "$(git status --porcelain)" ]] \
        || fail "Git working tree is not clean"

    pass "Git working tree is clean"
else
    printf 'INFO: Clean repository check is disabled for this run.\n'
fi

printf '\n--- Local quality checks ---\n'

uv run ruff format --check .
pass "Ruff format"

uv run ruff check .
pass "Ruff lint"

uv run mypy src tests
pass "mypy"

uv run pytest -m "not docker"
pass "Unit and Integration Tests"

printf '\n--- Docker configuration and build ---\n'

compose config --quiet
pass "Docker Compose configuration"

compose build
pass "Docker image build"

compose up -d
wait_for_readiness
verify_running_services
verify_migration
verify_port_exposure

./scripts/test-docker.sh
pass "Docker Smoke Tests"

verify_scheduler_worker_flow

printf '\n--- PostgreSQL persistence test ---\n'

revision_before="$(get_database_revision)"

compose down
compose up -d

wait_for_readiness
verify_running_services
verify_migration

revision_after="$(get_database_revision)"

[[ "${revision_before}" == "${revision_after}" ]] \
    || fail "Database revision did not survive container recreation"

[[ "${revision_after}" == "0001_baseline" ]] \
    || fail "Unexpected persisted revision: ${revision_after}"

pass "PostgreSQL data survived container recreation"

printf '\n========================================\n'
printf 'PHASE 0 ACCEPTANCE RESULT: PASS\n'
printf 'Log file: %s\n' "${LOG_FILE}"
printf 'Project G remains running after this test.\n'
printf '========================================\n'

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -f .env ]]; then
    echo ".env is required for Docker tests"
    exit 1
fi

uv run pytest -m docker --run-docker "$@"

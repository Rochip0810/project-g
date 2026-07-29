#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv run ruff check .
uv run mypy src tests
uv run pytest -m "not docker"

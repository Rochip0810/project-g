from typing import Any, cast

import httpx
import pytest

pytestmark = pytest.mark.docker


def test_compose_liveness(
    docker_base_url: str,
) -> None:
    response = httpx.get(
        f"{docker_base_url}/api/v1/health",
        timeout=5.0,
    )

    response.raise_for_status()

    payload = cast(dict[str, Any], response.json())

    assert payload["status"] == "healthy"
    assert payload["application"] == "project-g"


def test_compose_readiness(
    docker_base_url: str,
) -> None:
    response = httpx.get(
        f"{docker_base_url}/api/v1/health/readiness",
        timeout=5.0,
    )

    response.raise_for_status()

    payload = cast(dict[str, Any], response.json())
    checks = cast(dict[str, bool], payload["checks"])

    assert payload["status"] == "ready"
    assert checks == {
        "database": True,
        "redis": True,
        "migrations": True,
    }

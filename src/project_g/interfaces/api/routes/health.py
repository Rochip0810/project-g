from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from project_g.infrastructure.config import Settings

router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["healthy", "ready"]
    application: str
    version: str
    environment: str


def _get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)

    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are not configured")

    return settings


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check API liveness",
)
def health_check(request: Request) -> HealthResponse:
    settings = _get_settings(request)

    return HealthResponse(
        status="healthy",
        application=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
    )


@router.get(
    "/health/readiness",
    response_model=HealthResponse,
    summary="Check API readiness",
)
def readiness_check(request: Request) -> HealthResponse:
    settings = _get_settings(request)

    return HealthResponse(
        status="ready",
        application=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
    )

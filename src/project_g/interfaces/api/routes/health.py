from typing import Literal, cast

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from project_g.infrastructure.config import Settings
from project_g.monitoring import ReadinessProbe

router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["healthy"]
    application: str
    version: str
    environment: str


class DependencyChecks(BaseModel):
    database: bool
    redis: bool
    migrations: bool


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    application: str
    version: str
    environment: str
    checks: DependencyChecks


def _get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)

    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are not configured")

    return settings


def _get_readiness_probe(request: Request) -> ReadinessProbe:
    probe = getattr(request.app.state, "readiness_probe", None)

    if not callable(probe):
        raise RuntimeError("Readiness probe is not configured")

    return cast(ReadinessProbe, probe)


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
    response_model=ReadinessResponse,
    responses={503: {"description": "Service is not ready"}},
    summary="Check API readiness",
)
def readiness_check(
    request: Request,
    response: Response,
) -> ReadinessResponse:
    settings = _get_settings(request)
    report = _get_readiness_probe(request)()

    if not report.ready:
        response.status_code = 503

    return ReadinessResponse(
        status="ready" if report.ready else "not_ready",
        application=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
        checks=DependencyChecks(
            database=report.database,
            redis=report.redis,
            migrations=report.migrations,
        ),
    )

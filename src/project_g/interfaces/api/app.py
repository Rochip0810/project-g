from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from project_g.infrastructure.config import Settings, get_settings
from project_g.infrastructure.logging import configure_logging, get_logger
from project_g.interfaces.api.routes.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved_settings)
        logger = get_logger("project_g.api")

        logger.info(
            "application_started",
            event_name="application_started",
            status="running",
        )

        try:
            yield
        finally:
            logger.info(
                "application_stopped",
                event_name="application_stopped",
                status="stopped",
            )

    application = FastAPI(
        title="Project G API",
        description=("AI-powered automated media platform for Yomiuri Giants fans."),
        version=resolved_settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
    )

    application.state.settings = resolved_settings
    application.include_router(health_router)

    return application


app = create_app()

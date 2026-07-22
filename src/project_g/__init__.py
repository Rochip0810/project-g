import uvicorn

from project_g.infrastructure.config import get_settings


def main() -> None:
    settings = get_settings()

    uvicorn.run(
        "project_g.interfaces.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env.value == "development",
    )


__all__ = ["main"]

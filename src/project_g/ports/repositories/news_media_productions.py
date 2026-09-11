from typing import Protocol
from uuid import UUID

from project_g.domain.news.media_production import (
    NewsMediaProduction,
)


class NewsMediaProductionAlreadyExistsError(RuntimeError):
    """Raised when the same script generation/media version exists."""

    def __init__(
        self,
        script_generation_id: UUID,
        media_version: int,
    ) -> None:
        super().__init__(
            "Media production already exists for "
            f"script generation/version: "
            f"{script_generation_id}/{media_version}"
        )
        self.script_generation_id = script_generation_id
        self.media_version = media_version


class NewsMediaProductionNotFoundError(RuntimeError):
    """Raised when a media-production record cannot be found."""

    def __init__(
        self,
        media_production_id: UUID,
    ) -> None:
        super().__init__(f"Media production was not found: {media_production_id}")
        self.media_production_id = media_production_id


class NewsMediaProductionRepository(Protocol):
    def add(
        self,
        production: NewsMediaProduction,
    ) -> NewsMediaProduction:
        """Store and return a new media production."""
        ...

    def update(
        self,
        production: NewsMediaProduction,
    ) -> NewsMediaProduction:
        """Update and return an existing media production."""
        ...

    def get_by_media_production_id(
        self,
        media_production_id: UUID,
    ) -> NewsMediaProduction | None:
        """Return a media production by primary key."""
        ...

    def get_by_script_generation_version(
        self,
        *,
        script_generation_id: UUID,
        media_version: int,
    ) -> NewsMediaProduction | None:
        """Return media production for a script/version pair."""
        ...

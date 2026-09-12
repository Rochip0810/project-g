from datetime import datetime
from typing import Protocol
from uuid import UUID

from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
)


class NewsNarrationAudioAlreadyExistsError(RuntimeError):
    """Raised when the same media production/audio version exists."""

    def __init__(
        self,
        media_production_id: UUID,
        audio_version: int,
    ) -> None:
        super().__init__(
            "Narration audio already exists for "
            f"media production/version: "
            f"{media_production_id}/{audio_version}"
        )
        self.media_production_id = media_production_id
        self.audio_version = audio_version


class NewsNarrationAudioNotFoundError(RuntimeError):
    """Raised when a narration-audio generation cannot be found."""

    def __init__(
        self,
        audio_generation_id: UUID,
    ) -> None:
        super().__init__(f"Narration audio generation was not found: {audio_generation_id}")
        self.audio_generation_id = audio_generation_id


class NewsNarrationAudioGenerationRepository(Protocol):
    def add(
        self,
        generation: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
        """Store and return a new narration-audio generation."""
        ...

    def update(
        self,
        generation: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
        """Update and return an existing narration-audio generation."""
        ...

    def get_by_audio_generation_id(
        self,
        audio_generation_id: UUID,
    ) -> NewsNarrationAudioGeneration | None:
        """Return narration audio by primary key."""
        ...

    def get_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
    ) -> NewsNarrationAudioGeneration | None:
        """Return narration audio for a media-production/version pair."""
        ...

    def claim_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
    ) -> NewsNarrationAudioGeneration | None:
        """Atomically claim a ready or stale narration-audio generation."""
        ...

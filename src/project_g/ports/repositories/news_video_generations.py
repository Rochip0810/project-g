from datetime import datetime
from typing import Protocol
from uuid import UUID

from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
)


class NewsVideoGenerationAlreadyExistsError(RuntimeError):
    """Raised when the same media production/video version exists."""

    def __init__(
        self,
        media_production_id: UUID,
        video_version: int,
    ) -> None:
        super().__init__(
            "Video generation already exists for "
            f"media production/version: "
            f"{media_production_id}/{video_version}"
        )
        self.media_production_id = media_production_id
        self.video_version = video_version


class NewsVideoGenerationNotFoundError(RuntimeError):
    """Raised when a video-generation record cannot be found."""

    def __init__(
        self,
        video_generation_id: UUID,
    ) -> None:
        super().__init__(f"Video generation was not found: {video_generation_id}")
        self.video_generation_id = video_generation_id


class NewsVideoGenerationRepository(Protocol):
    def add(
        self,
        generation: NewsVideoGeneration,
    ) -> NewsVideoGeneration: ...

    def update(
        self,
        generation: NewsVideoGeneration,
    ) -> NewsVideoGeneration: ...

    def record_generated_if_current(
        self,
        *,
        video_generation_id: UUID,
        expected_attempt_number: int,
        storage_key: str,
        byte_size: int,
        content_sha256: str,
        duration_ms: int,
        completed_at: datetime,
    ) -> NewsVideoGeneration | None:
        """Complete only the currently owned generating attempt."""
        ...

    def mark_failed_if_current(
        self,
        *,
        video_generation_id: UUID,
        expected_attempt_number: int,
        reason: str,
        completed_at: datetime,
    ) -> NewsVideoGeneration | None:
        """Fail only the currently owned generating attempt."""
        ...

    def get_by_video_generation_id(
        self,
        video_generation_id: UUID,
    ) -> NewsVideoGeneration | None: ...

    def get_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        video_version: int,
    ) -> NewsVideoGeneration | None: ...

    def claim_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        video_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
        expected_attempt_number: int | None = None,
    ) -> NewsVideoGeneration | None: ...

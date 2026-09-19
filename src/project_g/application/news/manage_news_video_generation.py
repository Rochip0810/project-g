from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
)
from project_g.ports.repositories.news_video_generations import (
    NewsVideoGenerationAlreadyExistsError,
    NewsVideoGenerationNotFoundError,
    NewsVideoGenerationRepository,
)


class NewsVideoGenerationConfigurationMismatchError(RuntimeError):
    """Raised when persisted video configuration differs from requested input."""


class ManageNewsVideoGeneration:
    def __init__(
        self,
        *,
        repository: NewsVideoGenerationRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._id_factory = id_factory

    def prepare(
        self,
        *,
        media_production_id: UUID,
        video_version: int,
        renderer: str,
        video_format: str,
        width: int,
        height: int,
        fps: int,
        source_audio_generation_id: UUID,
        source_audio_sha256: str,
    ) -> NewsVideoGeneration:
        existing = self._repository.get_by_media_production_version(
            media_production_id=media_production_id,
            video_version=video_version,
        )

        if existing is not None:
            self._require_same_configuration(
                existing,
                renderer=renderer,
                video_format=video_format,
                width=width,
                height=height,
                fps=fps,
                source_audio_generation_id=source_audio_generation_id,
                source_audio_sha256=source_audio_sha256,
            )
            return existing

        pending = NewsVideoGeneration.pending(
            video_generation_id=self._id_factory(),
            media_production_id=media_production_id,
            video_version=video_version,
            renderer=renderer,
            video_format=video_format,
            width=width,
            height=height,
            fps=fps,
            source_audio_generation_id=source_audio_generation_id,
            source_audio_sha256=source_audio_sha256,
            created_at=self._clock(),
        )

        try:
            return self._repository.add(pending)
        except NewsVideoGenerationAlreadyExistsError:
            existing = self._repository.get_by_media_production_version(
                media_production_id=media_production_id,
                video_version=video_version,
            )

            if existing is None:
                raise

            self._require_same_configuration(
                existing,
                renderer=renderer,
                video_format=video_format,
                width=width,
                height=height,
                fps=fps,
                source_audio_generation_id=source_audio_generation_id,
                source_audio_sha256=source_audio_sha256,
            )

            return existing

    def claim(
        self,
        *,
        media_production_id: UUID,
        video_version: int,
        stale_after_seconds: int,
    ) -> NewsVideoGeneration | None:
        if stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be at least 1")

        started_at = self._clock()
        stale_before = started_at - timedelta(seconds=stale_after_seconds)

        return self._repository.claim_by_media_production_version(
            media_production_id=media_production_id,
            video_version=video_version,
            started_at=started_at,
            stale_before=stale_before,
        )

    def record_generated(
        self,
        *,
        video_generation_id: UUID,
        storage_key: str,
        byte_size: int,
        content_sha256: str,
        duration_ms: int,
    ) -> NewsVideoGeneration:
        generation = self._require_generation(video_generation_id)

        generated = generation.record_generated(
            storage_key=storage_key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            duration_ms=duration_ms,
            completed_at=self._clock(),
        )

        return self._repository.update(generated)

    def mark_failed(
        self,
        *,
        video_generation_id: UUID,
        reason: str,
    ) -> NewsVideoGeneration:
        generation = self._require_generation(video_generation_id)

        failed = generation.mark_failed(
            reason=reason,
            completed_at=self._clock(),
        )

        return self._repository.update(failed)

    def _require_generation(
        self,
        video_generation_id: UUID,
    ) -> NewsVideoGeneration:
        generation = self._repository.get_by_video_generation_id(video_generation_id)

        if generation is None:
            raise NewsVideoGenerationNotFoundError(video_generation_id)

        return generation

    @staticmethod
    def _require_same_configuration(
        generation: NewsVideoGeneration,
        *,
        renderer: str,
        video_format: str,
        width: int,
        height: int,
        fps: int,
        source_audio_generation_id: UUID,
        source_audio_sha256: str,
    ) -> None:
        requested = (
            renderer.strip(),
            video_format.strip().lower(),
            width,
            height,
            fps,
            source_audio_generation_id,
            source_audio_sha256.strip().lower(),
        )
        persisted = (
            generation.renderer,
            generation.video_format,
            generation.width,
            generation.height,
            generation.fps,
            generation.source_audio_generation_id,
            generation.source_audio_sha256,
        )

        if requested != persisted:
            raise NewsVideoGenerationConfigurationMismatchError(
                "Persisted video generation configuration does not match requested configuration"
            )

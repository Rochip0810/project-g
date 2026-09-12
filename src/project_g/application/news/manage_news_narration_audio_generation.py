from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
)
from project_g.ports.repositories.news_narration_audio_generations import (
    NewsNarrationAudioAlreadyExistsError,
    NewsNarrationAudioGenerationRepository,
    NewsNarrationAudioNotFoundError,
)

Clock = Callable[[], datetime]
AudioGenerationIdFactory = Callable[[], UUID]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NewsNarrationAudioConfigurationMismatchError(RuntimeError):
    """Raised when an existing generation has different immutable input."""

    def __init__(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
        field_name: str,
        expected: object,
        actual: object,
    ) -> None:
        super().__init__(
            "Narration audio configuration mismatch for "
            f"{media_production_id}/{audio_version}: "
            f"{field_name} existing={expected!r}, requested={actual!r}"
        )
        self.media_production_id = media_production_id
        self.audio_version = audio_version
        self.field_name = field_name
        self.expected = expected
        self.actual = actual


class ManageNewsNarrationAudioGeneration:
    def __init__(
        self,
        *,
        repository: NewsNarrationAudioGenerationRepository,
        clock: Clock = _utc_now,
        audio_generation_id_factory: AudioGenerationIdFactory = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._audio_generation_id_factory = audio_generation_id_factory

    def prepare(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
        provider: str,
        model: str,
        voice: str,
        audio_format: str,
        source_text_sha256: str,
    ) -> NewsNarrationAudioGeneration:
        existing = self._repository.get_by_media_production_version(
            media_production_id=media_production_id,
            audio_version=audio_version,
        )

        if existing is not None:
            requested = NewsNarrationAudioGeneration.pending(
                audio_generation_id=existing.audio_generation_id,
                media_production_id=media_production_id,
                audio_version=audio_version,
                provider=provider,
                model=model,
                voice=voice,
                audio_format=audio_format,
                source_text_sha256=source_text_sha256,
                created_at=existing.created_at,
            )
            return self._validate_configuration(
                existing,
                requested=requested,
            )

        generation = NewsNarrationAudioGeneration.pending(
            audio_generation_id=self._audio_generation_id_factory(),
            media_production_id=media_production_id,
            audio_version=audio_version,
            provider=provider,
            model=model,
            voice=voice,
            audio_format=audio_format,
            source_text_sha256=source_text_sha256,
            created_at=self._clock(),
        )

        try:
            return self._repository.add(generation)
        except NewsNarrationAudioAlreadyExistsError:
            existing = self._repository.get_by_media_production_version(
                media_production_id=media_production_id,
                audio_version=audio_version,
            )

            if existing is None:
                raise

            return self._validate_configuration(
                existing,
                requested=generation,
            )

    def claim(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
        stale_after_seconds: int | None = None,
    ) -> NewsNarrationAudioGeneration | None:
        started_at = self._clock()

        stale_before = None

        if stale_after_seconds is not None:
            if stale_after_seconds < 1:
                raise ValueError("stale_after_seconds must be at least 1")

            stale_before = started_at - timedelta(seconds=stale_after_seconds)

        return self._repository.claim_by_media_production_version(
            media_production_id=media_production_id,
            audio_version=audio_version,
            started_at=started_at,
            stale_before=stale_before,
        )

    def record_generated(
        self,
        *,
        audio_generation_id: UUID,
        storage_key: str,
        byte_size: int,
        content_sha256: str,
    ) -> NewsNarrationAudioGeneration:
        generation = self._get_generation(audio_generation_id)

        generated = generation.record_generated(
            storage_key=storage_key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            completed_at=self._clock(),
        )

        return self._repository.update(generated)

    def mark_failed(
        self,
        *,
        audio_generation_id: UUID,
        reason: str,
    ) -> NewsNarrationAudioGeneration:
        generation = self._get_generation(audio_generation_id)

        failed = generation.mark_failed(
            reason=reason,
            completed_at=self._clock(),
        )

        return self._repository.update(failed)

    def _get_generation(
        self,
        audio_generation_id: UUID,
    ) -> NewsNarrationAudioGeneration:
        generation = self._repository.get_by_audio_generation_id(audio_generation_id)

        if generation is None:
            raise NewsNarrationAudioNotFoundError(audio_generation_id)

        return generation

    def _validate_configuration(
        self,
        generation: NewsNarrationAudioGeneration,
        *,
        requested: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
        fields = (
            "provider",
            "model",
            "voice",
            "audio_format",
            "source_text_sha256",
        )

        for field_name in fields:
            expected = getattr(generation, field_name)
            actual = getattr(requested, field_name)

            if expected != actual:
                raise NewsNarrationAudioConfigurationMismatchError(
                    media_production_id=(generation.media_production_id),
                    audio_version=generation.audio_version,
                    field_name=field_name,
                    expected=expected,
                    actual=actual,
                )

        return generation

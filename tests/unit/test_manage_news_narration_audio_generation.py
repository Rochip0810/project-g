from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.manage_news_narration_audio_generation import (
    ManageNewsNarrationAudioGeneration,
    NewsNarrationAudioConfigurationMismatchError,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
    NewsNarrationAudioStatus,
)
from project_g.ports.repositories.news_narration_audio_generations import (
    NewsNarrationAudioAlreadyExistsError,
    NewsNarrationAudioNotFoundError,
)

_MEDIA_ID = UUID("75649b50-62e6-4d9e-a91a-678338667101")
_AUDIO_ID = UUID("75649b50-62e6-4d9e-a91a-678338667201")

_BASE_TIME = datetime(
    2026,
    9,
    12,
    8,
    0,
    tzinfo=UTC,
)

_SOURCE_HASH = "a" * 64
_CONTENT_HASH = "b" * 64


class FakeRepository:
    def __init__(
        self,
        generation: NewsNarrationAudioGeneration | None = None,
    ) -> None:
        self.generation = generation
        self.raise_duplicate_on_add = False

        self.claim_started_at: datetime | None = None
        self.claim_stale_before: datetime | None = None

    def add(
        self,
        generation: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
        if self.raise_duplicate_on_add:
            raise NewsNarrationAudioAlreadyExistsError(
                generation.media_production_id,
                generation.audio_version,
            )

        self.generation = generation
        return generation

    def update(
        self,
        generation: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
        self.generation = generation
        return generation

    def get_by_audio_generation_id(
        self,
        audio_generation_id: UUID,
    ) -> NewsNarrationAudioGeneration | None:
        if (
            self.generation is not None
            and self.generation.audio_generation_id == audio_generation_id
        ):
            return self.generation

        return None

    def get_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
    ) -> NewsNarrationAudioGeneration | None:
        if (
            self.generation is not None
            and self.generation.media_production_id == media_production_id
            and self.generation.audio_version == audio_version
        ):
            return self.generation

        return None

    def claim_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        audio_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
    ) -> NewsNarrationAudioGeneration | None:
        self.claim_started_at = started_at
        self.claim_stale_before = stale_before

        generation = self.get_by_media_production_version(
            media_production_id=media_production_id,
            audio_version=audio_version,
        )

        if generation is None:
            return None

        if generation.status not in {
            NewsNarrationAudioStatus.PENDING,
            NewsNarrationAudioStatus.FAILED,
        }:
            return None

        claimed = generation.start(started_at=started_at)
        self.generation = claimed
        return claimed


def _pending() -> NewsNarrationAudioGeneration:
    return NewsNarrationAudioGeneration.pending(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=_SOURCE_HASH,
        created_at=_BASE_TIME,
    )


def _manager(
    repository: FakeRepository,
    *,
    now: datetime = _BASE_TIME,
) -> ManageNewsNarrationAudioGeneration:
    return ManageNewsNarrationAudioGeneration(
        repository=repository,
        clock=lambda: now,
        audio_generation_id_factory=lambda: _AUDIO_ID,
    )


def test_prepare_creates_pending_generation() -> None:
    repository = FakeRepository()

    generation = _manager(repository).prepare(
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider=" openai ",
        model=" gpt-4o-mini-tts ",
        voice=" marin ",
        audio_format="MP3",
        source_text_sha256=_SOURCE_HASH.upper(),
    )

    assert generation.status is NewsNarrationAudioStatus.PENDING
    assert generation.audio_generation_id == _AUDIO_ID
    assert generation.provider == "openai"
    assert generation.audio_format == "mp3"
    assert generation.source_text_sha256 == _SOURCE_HASH


def test_prepare_returns_same_existing_generation() -> None:
    existing = _pending()
    repository = FakeRepository(existing)

    returned = _manager(repository).prepare(
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="MP3",
        source_text_sha256=_SOURCE_HASH.upper(),
    )

    assert returned == existing


def test_prepare_rejects_configuration_mismatch() -> None:
    existing = _pending()
    repository = FakeRepository(existing)

    with pytest.raises(
        NewsNarrationAudioConfigurationMismatchError,
        match="voice",
    ):
        _manager(repository).prepare(
            media_production_id=_MEDIA_ID,
            audio_version=1,
            provider="openai",
            model="gpt-4o-mini-tts",
            voice="cedar",
            audio_format="mp3",
            source_text_sha256=_SOURCE_HASH,
        )


def test_prepare_handles_duplicate_race() -> None:
    existing = _pending()
    repository = FakeRepository()
    repository.raise_duplicate_on_add = True

    original_add = repository.add

    def racing_add(
        generation: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
        repository.generation = existing
        return original_add(generation)

    repository.add = racing_add  # type: ignore[method-assign]

    returned = _manager(repository).prepare(
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=_SOURCE_HASH,
    )

    assert returned == existing


def test_claim_passes_stale_window() -> None:
    repository = FakeRepository(_pending())
    now = _BASE_TIME + timedelta(minutes=10)

    claimed = _manager(
        repository,
        now=now,
    ).claim(
        media_production_id=_MEDIA_ID,
        audio_version=1,
        stale_after_seconds=300,
    )

    assert claimed is not None
    assert claimed.status is NewsNarrationAudioStatus.GENERATING
    assert repository.claim_started_at == now
    assert repository.claim_stale_before == (now - timedelta(seconds=300))


def test_claim_rejects_invalid_stale_window() -> None:
    repository = FakeRepository(_pending())

    with pytest.raises(
        ValueError,
        match="stale_after_seconds must be at least 1",
    ):
        _manager(repository).claim(
            media_production_id=_MEDIA_ID,
            audio_version=1,
            stale_after_seconds=0,
        )


def test_record_generated_updates_generation() -> None:
    repository = FakeRepository(
        _pending().start(
            started_at=_BASE_TIME + timedelta(minutes=1),
        )
    )

    completed_at = _BASE_TIME + timedelta(minutes=2)

    generated = _manager(
        repository,
        now=completed_at,
    ).record_generated(
        audio_generation_id=_AUDIO_ID,
        storage_key=f"media/audio/{_MEDIA_ID}/v1.mp3",
        byte_size=12345,
        content_sha256=_CONTENT_HASH,
    )

    assert generated.status is NewsNarrationAudioStatus.GENERATED
    assert generated.byte_size == 12345
    assert generated.completed_at == completed_at


def test_mark_failed_updates_generation() -> None:
    repository = FakeRepository(
        _pending().start(
            started_at=_BASE_TIME + timedelta(minutes=1),
        )
    )

    failed = _manager(
        repository,
        now=_BASE_TIME + timedelta(minutes=2),
    ).mark_failed(
        audio_generation_id=_AUDIO_ID,
        reason="temporary failure",
    )

    assert failed.status is NewsNarrationAudioStatus.FAILED
    assert failed.failure_reason == "temporary failure"


def test_record_generated_rejects_unknown_generation() -> None:
    repository = FakeRepository()

    with pytest.raises(NewsNarrationAudioNotFoundError):
        _manager(repository).record_generated(
            audio_generation_id=_AUDIO_ID,
            storage_key="media/audio/example/v1.mp3",
            byte_size=123,
            content_sha256=_CONTENT_HASH,
        )

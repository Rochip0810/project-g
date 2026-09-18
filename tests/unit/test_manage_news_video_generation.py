from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.manage_news_video_generation import (
    ManageNewsVideoGeneration,
    NewsVideoGenerationConfigurationMismatchError,
)
from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
    NewsVideoGenerationStatus,
)
from project_g.ports.repositories.news_video_generations import (
    NewsVideoGenerationAlreadyExistsError,
    NewsVideoGenerationNotFoundError,
)

_MEDIA_ID = UUID("4c6c0652-d54b-4ddb-b16e-9e431ec90101")
_VIDEO_ID = UUID("4c6c0652-d54b-4ddb-b16e-9e431ec90201")

_NOW = datetime(
    2026,
    9,
    18,
    8,
    0,
    tzinfo=UTC,
)

_SOURCE_HASH = "a" * 64
_CONTENT_HASH = "b" * 64


class FakeRepository:
    def __init__(self) -> None:
        self.generation: NewsVideoGeneration | None = None
        self.raise_duplicate_once = False
        self.claim_calls: list[
            tuple[
                UUID,
                int,
                datetime,
                datetime | None,
            ]
        ] = []

    def add(
        self,
        generation: NewsVideoGeneration,
    ) -> NewsVideoGeneration:
        if self.raise_duplicate_once:
            self.raise_duplicate_once = False

            if self.generation is None:
                self.generation = generation

            raise NewsVideoGenerationAlreadyExistsError(
                generation.media_production_id,
                generation.video_version,
            )

        self.generation = generation
        return generation

    def update(
        self,
        generation: NewsVideoGeneration,
    ) -> NewsVideoGeneration:
        if (
            self.generation is None
            or self.generation.video_generation_id != generation.video_generation_id
        ):
            raise NewsVideoGenerationNotFoundError(generation.video_generation_id)

        self.generation = generation
        return generation

    def get_by_video_generation_id(
        self,
        video_generation_id: UUID,
    ) -> NewsVideoGeneration | None:
        if (
            self.generation is not None
            and self.generation.video_generation_id == video_generation_id
        ):
            return self.generation

        return None

    def get_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        video_version: int,
    ) -> NewsVideoGeneration | None:
        if (
            self.generation is not None
            and self.generation.media_production_id == media_production_id
            and self.generation.video_version == video_version
        ):
            return self.generation

        return None

    def claim_by_media_production_version(
        self,
        *,
        media_production_id: UUID,
        video_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
    ) -> NewsVideoGeneration | None:
        self.claim_calls.append(
            (
                media_production_id,
                video_version,
                started_at,
                stale_before,
            )
        )

        generation = self.get_by_media_production_version(
            media_production_id=media_production_id,
            video_version=video_version,
        )

        if generation is None:
            return None

        if generation.status not in {
            NewsVideoGenerationStatus.PENDING,
            NewsVideoGenerationStatus.FAILED,
        }:
            return None

        claimed = generation.start(started_at=started_at)
        self.generation = claimed

        return claimed


def _manager(
    repository: FakeRepository,
) -> ManageNewsVideoGeneration:
    return ManageNewsVideoGeneration(
        repository=repository,
        clock=lambda: _NOW,
        id_factory=lambda: _VIDEO_ID,
    )


def _prepare(
    manager: ManageNewsVideoGeneration,
) -> NewsVideoGeneration:
    return manager.prepare(
        media_production_id=_MEDIA_ID,
        video_version=1,
        renderer="ffmpeg",
        video_format="mp4",
        width=1080,
        height=1920,
        fps=30,
        source_audio_sha256=_SOURCE_HASH,
    )


def test_prepare_creates_pending_generation() -> None:
    repository = FakeRepository()

    generation = _prepare(_manager(repository))

    assert generation.video_generation_id == _VIDEO_ID
    assert generation.media_production_id == _MEDIA_ID
    assert generation.status is NewsVideoGenerationStatus.PENDING
    assert generation.renderer == "ffmpeg"
    assert generation.video_format == "mp4"
    assert generation.width == 1080
    assert generation.height == 1920
    assert generation.fps == 30
    assert generation.source_audio_sha256 == _SOURCE_HASH
    assert generation.created_at == _NOW


def test_prepare_is_idempotent() -> None:
    repository = FakeRepository()
    manager = _manager(repository)

    first = _prepare(manager)
    second = _prepare(manager)

    assert second == first


def test_prepare_normalizes_equivalent_configuration() -> None:
    repository = FakeRepository()
    manager = _manager(repository)

    first = _prepare(manager)

    second = manager.prepare(
        media_production_id=_MEDIA_ID,
        video_version=1,
        renderer=" ffmpeg ",
        video_format=" MP4 ",
        width=1080,
        height=1920,
        fps=30,
        source_audio_sha256=_SOURCE_HASH.upper(),
    )

    assert second == first


def test_prepare_rejects_configuration_mismatch() -> None:
    repository = FakeRepository()
    manager = _manager(repository)

    _prepare(manager)

    with pytest.raises(
        NewsVideoGenerationConfigurationMismatchError,
        match="does not match requested configuration",
    ):
        manager.prepare(
            media_production_id=_MEDIA_ID,
            video_version=1,
            renderer="ffmpeg",
            video_format="mp4",
            width=720,
            height=1280,
            fps=30,
            source_audio_sha256=_SOURCE_HASH,
        )


def test_prepare_recovers_from_duplicate_insert_race() -> None:
    repository = FakeRepository()
    repository.raise_duplicate_once = True

    generation = _prepare(_manager(repository))

    assert generation.video_generation_id == _VIDEO_ID
    assert repository.generation == generation


def test_claim_uses_stale_window() -> None:
    repository = FakeRepository()
    manager = _manager(repository)

    _prepare(manager)

    claimed = manager.claim(
        media_production_id=_MEDIA_ID,
        video_version=1,
        stale_after_seconds=180,
    )

    assert claimed is not None
    assert claimed.status is NewsVideoGenerationStatus.GENERATING
    assert claimed.attempt_count == 1

    assert repository.claim_calls == [
        (
            _MEDIA_ID,
            1,
            _NOW,
            datetime(
                2026,
                9,
                18,
                7,
                57,
                tzinfo=UTC,
            ),
        )
    ]


def test_claim_rejects_invalid_stale_window() -> None:
    repository = FakeRepository()

    with pytest.raises(
        ValueError,
        match="stale_after_seconds must be at least 1",
    ):
        _manager(repository).claim(
            media_production_id=_MEDIA_ID,
            video_version=1,
            stale_after_seconds=0,
        )


def test_record_generated_updates_generation() -> None:
    repository = FakeRepository()
    manager = _manager(repository)

    _prepare(manager)

    generating = manager.claim(
        media_production_id=_MEDIA_ID,
        video_version=1,
        stale_after_seconds=180,
    )

    assert generating is not None

    generated = manager.record_generated(
        video_generation_id=_VIDEO_ID,
        storage_key=f"media/video/{_MEDIA_ID}/v1.mp4",
        byte_size=23456,
        content_sha256=_CONTENT_HASH,
        duration_ms=12345,
    )

    assert generated.status is NewsVideoGenerationStatus.GENERATED
    assert generated.storage_key == (f"media/video/{_MEDIA_ID}/v1.mp4")
    assert generated.byte_size == 23456
    assert generated.content_sha256 == _CONTENT_HASH
    assert generated.duration_ms == 12345
    assert generated.completed_at == _NOW


def test_mark_failed_updates_generation() -> None:
    repository = FakeRepository()
    manager = _manager(repository)

    _prepare(manager)

    generating = manager.claim(
        media_production_id=_MEDIA_ID,
        video_version=1,
        stale_after_seconds=180,
    )

    assert generating is not None

    failed = manager.mark_failed(
        video_generation_id=_VIDEO_ID,
        reason="ffmpeg failed",
    )

    assert failed.status is NewsVideoGenerationStatus.FAILED
    assert failed.failure_reason == "ffmpeg failed"
    assert failed.completed_at == _NOW


def test_record_generated_rejects_unknown_generation() -> None:
    repository = FakeRepository()

    with pytest.raises(NewsVideoGenerationNotFoundError):
        _manager(repository).record_generated(
            video_generation_id=_VIDEO_ID,
            storage_key="media/video/example/v1.mp4",
            byte_size=23456,
            content_sha256=_CONTENT_HASH,
            duration_ms=12345,
        )


def test_mark_failed_rejects_unknown_generation() -> None:
    repository = FakeRepository()

    with pytest.raises(NewsVideoGenerationNotFoundError):
        _manager(repository).mark_failed(
            video_generation_id=_VIDEO_ID,
            reason="ffmpeg failed",
        )

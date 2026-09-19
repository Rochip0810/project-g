from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.domain.news.video_generation import (
    InvalidNewsVideoGenerationError,
    InvalidNewsVideoGenerationTransitionError,
    NewsVideoGeneration,
    NewsVideoGenerationStatus,
)

_CREATED_AT = datetime(2026, 9, 18, 0, 0, tzinfo=UTC)
_STARTED_AT = _CREATED_AT + timedelta(minutes=1)
_COMPLETED_AT = _CREATED_AT + timedelta(minutes=2)

_VIDEO_ID = UUID("bc70aa8a-a22d-4ea8-8df1-2db80d28e001")
_MEDIA_ID = UUID("bc70aa8a-a22d-4ea8-8df1-2db80d28e002")
_SOURCE_AUDIO_ID = UUID("bc70aa8a-a22d-4ea8-8df1-2db80d28e003")

_SOURCE_AUDIO_SHA256 = "a" * 64
_CONTENT_SHA256 = "b" * 64


def _pending() -> NewsVideoGeneration:
    return NewsVideoGeneration.pending(
        video_generation_id=_VIDEO_ID,
        media_production_id=_MEDIA_ID,
        video_version=1,
        renderer=" ffmpeg ",
        video_format=" MP4 ",
        width=1080,
        height=1920,
        fps=30,
        source_audio_generation_id=_SOURCE_AUDIO_ID,
        source_audio_sha256=_SOURCE_AUDIO_SHA256.upper(),
        created_at=_CREATED_AT,
    )


def _generating() -> NewsVideoGeneration:
    return _pending().start(started_at=_STARTED_AT)


def _generated() -> NewsVideoGeneration:
    return _generating().record_generated(
        storage_key="media/video/example/v1.mp4",
        byte_size=123456,
        content_sha256=_CONTENT_SHA256,
        duration_ms=12345,
        completed_at=_COMPLETED_AT,
    )


def test_pending_normalizes_configuration() -> None:
    generation = _pending()

    assert generation.status is NewsVideoGenerationStatus.PENDING
    assert generation.renderer == "ffmpeg"
    assert generation.video_format == "mp4"
    assert generation.source_audio_generation_id == _SOURCE_AUDIO_ID
    assert generation.source_audio_sha256 == _SOURCE_AUDIO_SHA256
    assert generation.width == 1080
    assert generation.height == 1920
    assert generation.fps == 30
    assert generation.attempt_count == 0
    assert generation.storage_key is None
    assert generation.duration_ms is None


def test_pending_can_start() -> None:
    generation = _pending().start(started_at=_STARTED_AT)

    assert generation.status is NewsVideoGenerationStatus.GENERATING
    assert generation.attempt_count == 1
    assert generation.started_at == _STARTED_AT
    assert generation.completed_at is None
    assert generation.failure_reason is None


def test_failed_generation_can_retry() -> None:
    failed = _generating().mark_failed(
        reason=" renderer failed ",
        completed_at=_COMPLETED_AT,
    )

    retried_at = _COMPLETED_AT + timedelta(minutes=1)
    retried = failed.start(started_at=retried_at)

    assert retried.status is NewsVideoGenerationStatus.GENERATING
    assert retried.attempt_count == 2
    assert retried.started_at == retried_at
    assert retried.failure_reason is None


def test_generating_can_record_generated_video() -> None:
    generation = _generated()

    assert generation.status is NewsVideoGenerationStatus.GENERATED
    assert generation.storage_key == "media/video/example/v1.mp4"
    assert generation.byte_size == 123456
    assert generation.content_sha256 == _CONTENT_SHA256
    assert generation.duration_ms == 12345
    assert generation.completed_at == _COMPLETED_AT


def test_generating_can_mark_failed() -> None:
    generation = _generating().mark_failed(
        reason=" renderer failed ",
        completed_at=_COMPLETED_AT,
    )

    assert generation.status is NewsVideoGenerationStatus.FAILED
    assert generation.failure_reason == "renderer failed"
    assert generation.storage_key is None
    assert generation.byte_size is None
    assert generation.content_sha256 is None
    assert generation.duration_ms is None


def test_video_version_must_be_positive() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="video_version must be at least 1",
    ):
        replace(
            _pending(),
            video_version=0,
        )


def test_width_must_be_positive() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="width must be at least 1",
    ):
        replace(
            _pending(),
            width=0,
        )


def test_height_must_be_positive() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="height must be at least 1",
    ):
        replace(
            _pending(),
            height=0,
        )


def test_fps_must_be_positive() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="fps must be at least 1",
    ):
        replace(
            _pending(),
            fps=0,
        )


def test_invalid_source_audio_sha256_is_rejected() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="source_audio_sha256 must be a 64-character SHA-256 hex digest",
    ):
        replace(
            _pending(),
            source_audio_sha256="not-a-hash",
        )


def test_generated_video_requires_complete_artifact_metadata() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="generated video must include complete artifact metadata",
    ):
        replace(
            _generated(),
            duration_ms=None,
        )


def test_byte_size_must_be_positive() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="byte_size must be at least 1",
    ):
        replace(
            _generated(),
            byte_size=0,
        )


def test_duration_must_be_positive() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="duration_ms must be at least 1",
    ):
        replace(
            _generated(),
            duration_ms=0,
        )


def test_generated_video_cannot_start_again() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationTransitionError,
        match="Video generation can only start from pending or failed",
    ):
        _generated().start(
            started_at=_COMPLETED_AT + timedelta(minutes=1),
        )


def test_pending_video_cannot_record_generated_artifact() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationTransitionError,
        match="Video generation must be generating",
    ):
        _pending().record_generated(
            storage_key="media/video/example/v1.mp4",
            byte_size=123456,
            content_sha256=_CONTENT_SHA256,
            duration_ms=12345,
            completed_at=_COMPLETED_AT,
        )


def test_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(
        InvalidNewsVideoGenerationError,
        match="created_at must be timezone-aware",
    ):
        replace(
            _pending(),
            created_at=datetime(2026, 9, 18, 0, 0),
        )

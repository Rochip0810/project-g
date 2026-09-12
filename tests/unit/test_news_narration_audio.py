from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.domain.news.narration_audio import (
    InvalidNewsNarrationAudioError,
    InvalidNewsNarrationAudioTransitionError,
    NewsNarrationAudioGeneration,
    NewsNarrationAudioStatus,
)

_AUDIO_ID = UUID("18e9fe24-4b71-4569-bcf2-0700c34d1001")
_MEDIA_ID = UUID("18e9fe24-4b71-4569-bcf2-0700c34d2001")
_BASE_TIME = datetime(2026, 9, 12, 6, 0, tzinfo=UTC)
_SOURCE_HASH = "a" * 64
_CONTENT_HASH = "b" * 64


def _pending() -> NewsNarrationAudioGeneration:
    return NewsNarrationAudioGeneration.pending(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="MP3",
        source_text_sha256=_SOURCE_HASH.upper(),
        created_at=_BASE_TIME,
    )


def test_pending_normalizes_configuration() -> None:
    generation = _pending()

    assert generation.status is NewsNarrationAudioStatus.PENDING
    assert generation.attempt_count == 0
    assert generation.audio_format == "mp3"
    assert generation.source_text_sha256 == _SOURCE_HASH
    assert generation.storage_key is None
    assert generation.byte_size is None
    assert generation.content_sha256 is None


def test_generated_lifecycle_persists_artifact_metadata() -> None:
    started_at = _BASE_TIME + timedelta(minutes=1)
    completed_at = _BASE_TIME + timedelta(minutes=2)

    generated = (
        _pending()
        .start(
            started_at=started_at,
        )
        .record_generated(
            storage_key=f"media/audio/{_MEDIA_ID}/v1.mp3",
            byte_size=12345,
            content_sha256=_CONTENT_HASH,
            completed_at=completed_at,
        )
    )

    assert generated.status is NewsNarrationAudioStatus.GENERATED
    assert generated.attempt_count == 1
    assert generated.started_at == started_at
    assert generated.completed_at == completed_at
    assert generated.storage_key == f"media/audio/{_MEDIA_ID}/v1.mp3"
    assert generated.byte_size == 12345
    assert generated.content_sha256 == _CONTENT_HASH
    assert generated.failure_reason is None


def test_failed_generation_can_retry() -> None:
    failed = (
        _pending()
        .start(
            started_at=_BASE_TIME + timedelta(minutes=1),
        )
        .mark_failed(
            reason=" TTS temporarily unavailable ",
            completed_at=_BASE_TIME + timedelta(minutes=2),
        )
    )

    assert failed.status is NewsNarrationAudioStatus.FAILED
    assert failed.failure_reason == "TTS temporarily unavailable"

    retried = failed.start(
        started_at=_BASE_TIME + timedelta(minutes=3),
    )

    assert retried.status is NewsNarrationAudioStatus.GENERATING
    assert retried.attempt_count == 2
    assert retried.failure_reason is None
    assert retried.completed_at is None


def test_start_rejects_generating_generation() -> None:
    generating = _pending().start(
        started_at=_BASE_TIME + timedelta(minutes=1),
    )

    with pytest.raises(
        InvalidNewsNarrationAudioTransitionError,
        match="only start from pending or failed",
    ):
        generating.start(
            started_at=_BASE_TIME + timedelta(minutes=2),
        )


def test_record_generated_rejects_pending_generation() -> None:
    with pytest.raises(
        InvalidNewsNarrationAudioTransitionError,
        match="must be generating",
    ):
        _pending().record_generated(
            storage_key="media/audio/example/v1.mp3",
            byte_size=1,
            content_sha256=_CONTENT_HASH,
            completed_at=_BASE_TIME + timedelta(minutes=1),
        )


@pytest.mark.parametrize(
    "source_hash",
    (
        "",
        "a" * 63,
        "z" * 64,
    ),
)
def test_invalid_source_text_sha256_is_rejected(
    source_hash: str,
) -> None:
    with pytest.raises(
        InvalidNewsNarrationAudioError,
        match="source_text_sha256",
    ):
        NewsNarrationAudioGeneration.pending(
            audio_generation_id=_AUDIO_ID,
            media_production_id=_MEDIA_ID,
            audio_version=1,
            provider="openai",
            model="gpt-4o-mini-tts",
            voice="marin",
            audio_format="mp3",
            source_text_sha256=source_hash,
            created_at=_BASE_TIME,
        )


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(
        InvalidNewsNarrationAudioError,
        match="created_at must be timezone-aware",
    ):
        NewsNarrationAudioGeneration.pending(
            audio_generation_id=_AUDIO_ID,
            media_production_id=_MEDIA_ID,
            audio_version=1,
            provider="openai",
            model="gpt-4o-mini-tts",
            voice="marin",
            audio_format="mp3",
            source_text_sha256=_SOURCE_HASH,
            created_at=datetime(2026, 9, 12, 6, 0),
        )


def test_completion_before_start_is_rejected() -> None:
    generating = _pending().start(
        started_at=_BASE_TIME + timedelta(minutes=2),
    )

    with pytest.raises(
        InvalidNewsNarrationAudioError,
        match="completed_at must not be earlier than started_at",
    ):
        generating.record_generated(
            storage_key="media/audio/example/v1.mp3",
            byte_size=100,
            content_sha256=_CONTENT_HASH,
            completed_at=_BASE_TIME + timedelta(minutes=1),
        )


def test_generated_requires_positive_byte_size() -> None:
    generating = _pending().start(
        started_at=_BASE_TIME + timedelta(minutes=1),
    )

    with pytest.raises(
        InvalidNewsNarrationAudioError,
        match="byte_size must be at least 1",
    ):
        generating.record_generated(
            storage_key="media/audio/example/v1.mp3",
            byte_size=0,
            content_sha256=_CONTENT_HASH,
            completed_at=_BASE_TIME + timedelta(minutes=2),
        )


def test_generated_requires_complete_artifact_metadata() -> None:
    with pytest.raises(
        InvalidNewsNarrationAudioError,
        match="complete artifact metadata",
    ):
        NewsNarrationAudioGeneration(
            audio_generation_id=_AUDIO_ID,
            media_production_id=_MEDIA_ID,
            audio_version=1,
            status=NewsNarrationAudioStatus.GENERATED,
            provider="openai",
            model="gpt-4o-mini-tts",
            voice="marin",
            audio_format="mp3",
            source_text_sha256=_SOURCE_HASH,
            attempt_count=1,
            storage_key="media/audio/example/v1.mp3",
            byte_size=100,
            content_sha256=None,
            failure_reason=None,
            created_at=_BASE_TIME,
            started_at=_BASE_TIME + timedelta(minutes=1),
            completed_at=_BASE_TIME + timedelta(minutes=2),
            updated_at=_BASE_TIME + timedelta(minutes=2),
        )

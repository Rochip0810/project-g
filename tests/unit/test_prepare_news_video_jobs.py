from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.manage_news_video_generation import (
    NewsVideoGenerationConfigurationMismatchError,
)
from project_g.application.news.prepare_news_video_jobs import (
    PrepareNewsVideoJobs,
    PrepareNewsVideoJobsResult,
)
from project_g.domain.news.media_production import NewsMediaProduction
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
)
from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
    NewsVideoGenerationStatus,
)
from project_g.ports.repositories.news_video_candidates import (
    NewsVideoCandidate,
)

_BASE_TIME = datetime(2026, 9, 19, 0, 0, tzinfo=UTC)

_MEDIA_ID = UUID("11111111-1111-4111-8111-000000000301")
_SCRIPT_ID = UUID("11111111-1111-4111-8111-000000000201")
_AUDIO_ID = UUID("11111111-1111-4111-8111-000000000401")
_VIDEO_ID = UUID("11111111-1111-4111-8111-000000000501")

_AUDIO_HASH = "a" * 64
_OTHER_HASH = "b" * 64
_TEXT_HASH = "c" * 64


def _time(minutes: int) -> datetime:
    return _BASE_TIME + timedelta(minutes=minutes)


def _media() -> NewsMediaProduction:
    return NewsMediaProduction.pending(
        media_production_id=_MEDIA_ID,
        script_generation_id=_SCRIPT_ID,
        media_version=1,
        created_at=_time(0),
    ).start(started_at=_time(1))


def _audio(
    *,
    generated: bool = True,
    audio_version: int = 1,
) -> NewsNarrationAudioGeneration:
    pending = NewsNarrationAudioGeneration.pending(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=audio_version,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=_TEXT_HASH,
        created_at=_time(2),
    )

    if not generated:
        return pending

    return pending.start(
        started_at=_time(3),
    ).record_generated(
        storage_key=f"media/audio/{_MEDIA_ID}/v{audio_version}.mp3",
        byte_size=12345,
        content_sha256=_AUDIO_HASH,
        completed_at=_time(4),
    )


def _candidate(
    *,
    generated_audio: bool = True,
    audio_version: int = 1,
) -> NewsVideoCandidate:
    return NewsVideoCandidate(
        media_production=_media(),
        source_audio=_audio(
            generated=generated_audio,
            audio_version=audio_version,
        ),
    )


class FakeCandidateRepository:
    def __init__(
        self,
        candidates: tuple[NewsVideoCandidate, ...],
    ) -> None:
        self.candidates = candidates
        self.calls: list[tuple[int, int, datetime, int]] = []

    def list_candidates(
        self,
        *,
        audio_version: int,
        video_version: int,
        stale_before: datetime,
        limit: int,
    ) -> tuple[NewsVideoCandidate, ...]:
        self.calls.append(
            (
                audio_version,
                video_version,
                stale_before,
                limit,
            )
        )
        return self.candidates


class FakeGenerationRepository:
    def __init__(self) -> None:
        self.generation: NewsVideoGeneration | None = None
        self.add_count = 0

    def add(
        self,
        generation: NewsVideoGeneration,
    ) -> NewsVideoGeneration:
        self.add_count += 1
        self.generation = generation
        return generation

    def update(
        self,
        generation: NewsVideoGeneration,
    ) -> NewsVideoGeneration:
        self.generation = generation
        return generation

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
        current = self.get_by_video_generation_id(video_generation_id)

        if current is None:
            return None

        if (
            current.status is not NewsVideoGenerationStatus.GENERATING
            or current.attempt_count != expected_attempt_number
        ):
            return None

        generated = current.record_generated(
            storage_key=storage_key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            duration_ms=duration_ms,
            completed_at=completed_at,
        )

        return self.update(generated)

    def mark_failed_if_current(
        self,
        *,
        video_generation_id: UUID,
        expected_attempt_number: int,
        reason: str,
        completed_at: datetime,
    ) -> NewsVideoGeneration | None:
        current = self.get_by_video_generation_id(video_generation_id)

        if current is None:
            return None

        if (
            current.status is not NewsVideoGenerationStatus.GENERATING
            or current.attempt_count != expected_attempt_number
        ):
            return None

        failed = current.mark_failed(
            reason=reason,
            completed_at=completed_at,
        )

        return self.update(failed)

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
        expected_attempt_number: int | None = None,
    ) -> NewsVideoGeneration | None:
        return None


def _prepare(
    candidate_repository: FakeCandidateRepository,
    generation_repository: FakeGenerationRepository,
) -> PrepareNewsVideoJobs:
    return PrepareNewsVideoJobs(
        candidate_repository=candidate_repository,
        generation_repository=generation_repository,
        clock=lambda: _time(5),
        video_generation_id_factory=lambda: _VIDEO_ID,
    )


def _execute(
    preparer: PrepareNewsVideoJobs,
    *,
    audio_version: int = 1,
    video_version: int = 1,
) -> PrepareNewsVideoJobsResult:
    return preparer.execute(
        audio_version=audio_version,
        video_version=video_version,
        stale_before=_time(10),
        limit=10,
        renderer="ffmpeg",
        video_format="mp4",
        width=1080,
        height=1920,
        fps=30,
    )


def test_prepare_creates_video_from_exact_audio_source() -> None:
    candidates = FakeCandidateRepository((_candidate(),))
    generations = FakeGenerationRepository()

    result = _execute(_prepare(candidates, generations))

    assert result.candidate_count == 1
    assert result.prepared_count == 1
    assert len(result.jobs) == 1

    job = result.jobs[0]

    assert job.video_generation_id == _VIDEO_ID
    assert job.media_production_id == _MEDIA_ID
    assert job.video_version == 1
    assert job.next_attempt_number == 1

    generation = generations.generation

    assert generation is not None
    assert generation.status is NewsVideoGenerationStatus.PENDING
    assert generation.source_audio_generation_id == _AUDIO_ID
    assert generation.source_audio_sha256 == _AUDIO_HASH
    assert generation.width == 1080
    assert generation.height == 1920
    assert generation.fps == 30

    assert candidates.calls == [(1, 1, _time(10), 10)]


def test_prepare_reuses_existing_pending_generation() -> None:
    candidates = FakeCandidateRepository((_candidate(),))
    generations = FakeGenerationRepository()
    preparer = _prepare(candidates, generations)

    first = _execute(preparer)
    second = _execute(preparer)

    assert first.jobs == second.jobs
    assert generations.add_count == 1


def test_prepare_skips_already_generated_video() -> None:
    candidates = FakeCandidateRepository((_candidate(),))
    generations = FakeGenerationRepository()
    preparer = _prepare(candidates, generations)

    _execute(preparer)

    pending = generations.generation
    assert pending is not None

    generations.update(
        pending.start(
            started_at=_time(6),
        ).record_generated(
            storage_key=f"media/video/{_MEDIA_ID}/v1.mp4",
            byte_size=23456,
            content_sha256=_OTHER_HASH,
            duration_ms=12345,
            completed_at=_time(7),
        )
    )

    result = _execute(preparer)

    assert result.candidate_count == 1
    assert result.prepared_count == 0
    assert result.jobs == ()
    assert generations.add_count == 1


def test_prepare_retries_failed_generation_with_next_attempt() -> None:
    candidates = FakeCandidateRepository((_candidate(),))
    generations = FakeGenerationRepository()
    preparer = _prepare(candidates, generations)

    _execute(preparer)

    pending = generations.generation
    assert pending is not None

    generations.update(
        pending.start(
            started_at=_time(6),
        ).mark_failed(
            reason="FFmpeg failed",
            completed_at=_time(7),
        )
    )

    result = _execute(preparer)

    assert result.prepared_count == 1
    assert result.jobs[0].video_generation_id == _VIDEO_ID
    assert result.jobs[0].next_attempt_number == 2
    assert generations.add_count == 1


def test_prepare_skips_unfinished_audio() -> None:
    candidates = FakeCandidateRepository((_candidate(generated_audio=False),))
    generations = FakeGenerationRepository()

    result = _execute(_prepare(candidates, generations))

    assert result.candidate_count == 1
    assert result.prepared_count == 0
    assert result.jobs == ()
    assert generations.generation is None


def test_prepare_skips_mismatched_audio_version() -> None:
    candidates = FakeCandidateRepository((_candidate(audio_version=2),))
    generations = FakeGenerationRepository()

    result = _execute(
        _prepare(candidates, generations),
        audio_version=1,
    )

    assert result.candidate_count == 1
    assert result.prepared_count == 0
    assert generations.generation is None


def test_prepare_skips_audio_from_different_media_production() -> None:
    candidate = _candidate()

    other_audio = replace(
        candidate.source_audio,
        media_production_id=UUID("11111111-1111-4111-8111-000000000999"),
    )

    candidates = FakeCandidateRepository(
        (
            NewsVideoCandidate(
                media_production=candidate.media_production,
                source_audio=other_audio,
            ),
        )
    )
    generations = FakeGenerationRepository()

    result = _execute(_prepare(candidates, generations))

    assert result.candidate_count == 1
    assert result.prepared_count == 0
    assert generations.generation is None


def test_prepare_rejects_existing_video_with_different_audio() -> None:
    candidates = FakeCandidateRepository((_candidate(),))
    generations = FakeGenerationRepository()
    preparer = _prepare(candidates, generations)

    _execute(preparer)

    original = candidates.candidates[0]

    candidates.candidates = (
        NewsVideoCandidate(
            media_production=original.media_production,
            source_audio=replace(
                original.source_audio,
                content_sha256=_OTHER_HASH,
            ),
        ),
    )

    with pytest.raises(
        NewsVideoGenerationConfigurationMismatchError,
        match="does not match requested configuration",
    ):
        _execute(preparer)

    assert generations.add_count == 1

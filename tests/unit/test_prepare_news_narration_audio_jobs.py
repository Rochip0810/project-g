from datetime import UTC, datetime, timedelta
from uuid import UUID

from project_g.application.news.prepare_news_narration_audio_jobs import (
    PrepareNewsNarrationAudioJobs,
)
from project_g.domain.news.media_production import (
    NewsMediaProduction,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
    NewsNarrationAudioStatus,
)
from project_g.ports.repositories.news_narration_audio_candidates import (
    NewsNarrationAudioCandidate,
)

_MEDIA_ID = UUID("a8d33016-b2cc-4e29-8557-373319990101")
_SCRIPT_ID = UUID("a8d33016-b2cc-4e29-8557-373319990201")
_AUDIO_ID = UUID("a8d33016-b2cc-4e29-8557-373319990301")

_BASE_TIME = datetime(
    2026,
    9,
    12,
    10,
    0,
    tzinfo=UTC,
)

_CONTENT_HASH = "b" * 64


def _media() -> NewsMediaProduction:
    return NewsMediaProduction.pending(
        media_production_id=_MEDIA_ID,
        script_generation_id=_SCRIPT_ID,
        media_version=1,
        created_at=_BASE_TIME,
    )


class FakeCandidateRepository:
    def __init__(
        self,
        candidates: tuple[NewsNarrationAudioCandidate, ...],
    ) -> None:
        self.candidates = candidates

    def list_candidates(
        self,
        *,
        audio_version: int,
        stale_before: datetime,
        limit: int,
    ) -> tuple[NewsNarrationAudioCandidate, ...]:
        return self.candidates[:limit]


class FakeGenerationRepository:
    def __init__(
        self,
        generation: NewsNarrationAudioGeneration | None = None,
    ) -> None:
        self.generation = generation

    def add(
        self,
        generation: NewsNarrationAudioGeneration,
    ) -> NewsNarrationAudioGeneration:
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
        raise AssertionError("claim must not be called while preparing jobs")


def _service(
    *,
    candidate_repository: FakeCandidateRepository,
    generation_repository: FakeGenerationRepository,
) -> PrepareNewsNarrationAudioJobs:
    return PrepareNewsNarrationAudioJobs(
        candidate_repository=candidate_repository,
        generation_repository=generation_repository,
        clock=lambda: _BASE_TIME + timedelta(minutes=1),
        audio_generation_id_factory=lambda: _AUDIO_ID,
    )


def test_prepare_creates_durable_audio_job() -> None:
    candidate = NewsNarrationAudioCandidate(
        media_production=_media(),
        full_narration=" Project Gの完成ナレーション ",
    )
    candidate_repository = FakeCandidateRepository((candidate,))
    generation_repository = FakeGenerationRepository()

    result = _service(
        candidate_repository=candidate_repository,
        generation_repository=generation_repository,
    ).execute(
        audio_version=1,
        stale_before=_BASE_TIME,
        limit=5,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
    )

    assert result.candidate_count == 1
    assert result.prepared_count == 1
    assert len(result.jobs) == 1

    job = result.jobs[0]

    assert job.audio_generation_id == _AUDIO_ID
    assert job.media_production_id == _MEDIA_ID
    assert job.audio_version == 1
    assert job.next_attempt_number == 1

    stored = generation_repository.generation
    assert stored is not None
    assert stored.status is NewsNarrationAudioStatus.PENDING

    expected_hash = "0a3d6f75f806d9ce0961f828e126360dc3b1dd9fd8a0fe447b64e39b187d5c07"

    assert stored.source_text_sha256 == expected_hash


def test_prepare_failed_audio_uses_next_attempt() -> None:
    pending = NewsNarrationAudioGeneration.pending(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=("0a3d6f75f806d9ce0961f828e126360dc3b1dd9fd8a0fe447b64e39b187d5c07"),
        created_at=_BASE_TIME,
    )

    failed = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=1),
    ).mark_failed(
        reason="temporary TTS failure",
        completed_at=_BASE_TIME + timedelta(minutes=2),
    )

    candidate_repository = FakeCandidateRepository(
        (
            NewsNarrationAudioCandidate(
                media_production=_media(),
                full_narration=("Project Gの完成ナレーション"),
            ),
        )
    )
    generation_repository = FakeGenerationRepository(failed)

    result = _service(
        candidate_repository=candidate_repository,
        generation_repository=generation_repository,
    ).execute(
        audio_version=1,
        stale_before=_BASE_TIME,
        limit=5,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
    )

    assert result.prepared_count == 1
    assert result.jobs[0].next_attempt_number == 2


def test_prepare_stale_generating_uses_next_attempt() -> None:
    pending = NewsNarrationAudioGeneration.pending(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=("0a3d6f75f806d9ce0961f828e126360dc3b1dd9fd8a0fe447b64e39b187d5c07"),
        created_at=_BASE_TIME,
    )

    generating = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=1),
    )

    candidate_repository = FakeCandidateRepository(
        (
            NewsNarrationAudioCandidate(
                media_production=_media(),
                full_narration=("Project Gの完成ナレーション"),
            ),
        )
    )
    generation_repository = FakeGenerationRepository(generating)

    result = _service(
        candidate_repository=candidate_repository,
        generation_repository=generation_repository,
    ).execute(
        audio_version=1,
        stale_before=_BASE_TIME,
        limit=5,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
    )

    assert result.prepared_count == 1
    assert result.jobs[0].next_attempt_number == 2


def test_prepare_defensively_skips_generated_audio() -> None:
    pending = NewsNarrationAudioGeneration.pending(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=("0a3d6f75f806d9ce0961f828e126360dc3b1dd9fd8a0fe447b64e39b187d5c07"),
        created_at=_BASE_TIME,
    )

    generated = pending.start(
        started_at=_BASE_TIME + timedelta(minutes=1),
    ).record_generated(
        storage_key="media/audio/example/v1.mp3",
        byte_size=100,
        content_sha256=_CONTENT_HASH,
        completed_at=_BASE_TIME + timedelta(minutes=2),
    )

    candidate_repository = FakeCandidateRepository(
        (
            NewsNarrationAudioCandidate(
                media_production=_media(),
                full_narration=("Project Gの完成ナレーション"),
            ),
        )
    )
    generation_repository = FakeGenerationRepository(generated)

    result = _service(
        candidate_repository=candidate_repository,
        generation_repository=generation_repository,
    ).execute(
        audio_version=1,
        stale_before=_BASE_TIME,
        limit=5,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
    )

    assert result.candidate_count == 1
    assert result.prepared_count == 0
    assert result.jobs == ()


def test_prepare_skips_blank_candidate_narration() -> None:
    candidate_repository = FakeCandidateRepository(
        (
            NewsNarrationAudioCandidate(
                media_production=_media(),
                full_narration="   ",
            ),
        )
    )
    generation_repository = FakeGenerationRepository()

    result = _service(
        candidate_repository=candidate_repository,
        generation_repository=generation_repository,
    ).execute(
        audio_version=1,
        stale_before=_BASE_TIME,
        limit=5,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
    )

    assert result.candidate_count == 1
    assert result.prepared_count == 0
    assert generation_repository.generation is None

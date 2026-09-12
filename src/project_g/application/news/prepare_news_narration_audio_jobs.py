from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4

from project_g.application.news.manage_news_narration_audio_generation import (
    ManageNewsNarrationAudioGeneration,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioStatus,
)
from project_g.ports.repositories.news_narration_audio_candidates import (
    NewsNarrationAudioCandidateRepository,
)
from project_g.ports.repositories.news_narration_audio_generations import (
    NewsNarrationAudioGenerationRepository,
)

AudioGenerationIdFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class PreparedNewsNarrationAudioJob:
    audio_generation_id: UUID
    media_production_id: UUID
    audio_version: int
    next_attempt_number: int


@dataclass(frozen=True, slots=True)
class PrepareNewsNarrationAudioJobsResult:
    candidate_count: int
    prepared_count: int
    jobs: tuple[PreparedNewsNarrationAudioJob, ...]


class PrepareNewsNarrationAudioJobs:
    def __init__(
        self,
        *,
        candidate_repository: NewsNarrationAudioCandidateRepository,
        generation_repository: NewsNarrationAudioGenerationRepository,
        clock: Callable[[], datetime],
        audio_generation_id_factory: AudioGenerationIdFactory = uuid4,
    ) -> None:
        self._candidate_repository = candidate_repository
        self._generation_repository = generation_repository
        self._clock = clock
        self._audio_generation_id_factory = audio_generation_id_factory

    def execute(
        self,
        *,
        audio_version: int,
        stale_before: datetime,
        limit: int,
        provider: str,
        model: str,
        voice: str,
        audio_format: str,
    ) -> PrepareNewsNarrationAudioJobsResult:
        candidates = self._candidate_repository.list_candidates(
            audio_version=audio_version,
            stale_before=stale_before,
            limit=limit,
        )

        manager = ManageNewsNarrationAudioGeneration(
            repository=self._generation_repository,
            clock=self._clock,
            audio_generation_id_factory=(self._audio_generation_id_factory),
        )

        jobs: list[PreparedNewsNarrationAudioJob] = []

        for candidate in candidates:
            full_narration = candidate.full_narration.strip()

            if not full_narration:
                continue

            source_text_sha256 = sha256(full_narration.encode("utf-8")).hexdigest()

            production = candidate.media_production

            generation = manager.prepare(
                media_production_id=(production.media_production_id),
                audio_version=audio_version,
                provider=provider,
                model=model,
                voice=voice,
                audio_format=audio_format,
                source_text_sha256=source_text_sha256,
            )

            if generation.status is NewsNarrationAudioStatus.GENERATED:
                continue

            jobs.append(
                PreparedNewsNarrationAudioJob(
                    audio_generation_id=(generation.audio_generation_id),
                    media_production_id=(generation.media_production_id),
                    audio_version=generation.audio_version,
                    next_attempt_number=(generation.attempt_count + 1),
                )
            )

        return PrepareNewsNarrationAudioJobsResult(
            candidate_count=len(candidates),
            prepared_count=len(jobs),
            jobs=tuple(jobs),
        )

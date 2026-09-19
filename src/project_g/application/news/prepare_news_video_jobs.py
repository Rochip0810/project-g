from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from project_g.application.news.manage_news_video_generation import (
    ManageNewsVideoGeneration,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioStatus,
)
from project_g.domain.news.video_generation import (
    NewsVideoGenerationStatus,
)
from project_g.ports.repositories.news_video_candidates import (
    NewsVideoCandidateRepository,
)
from project_g.ports.repositories.news_video_generations import (
    NewsVideoGenerationRepository,
)

VideoGenerationIdFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class PreparedNewsVideoJob:
    video_generation_id: UUID
    media_production_id: UUID
    video_version: int
    next_attempt_number: int


@dataclass(frozen=True, slots=True)
class PrepareNewsVideoJobsResult:
    candidate_count: int
    prepared_count: int
    jobs: tuple[PreparedNewsVideoJob, ...]


class PrepareNewsVideoJobs:
    def __init__(
        self,
        *,
        candidate_repository: NewsVideoCandidateRepository,
        generation_repository: NewsVideoGenerationRepository,
        clock: Callable[[], datetime],
        video_generation_id_factory: VideoGenerationIdFactory = uuid4,
    ) -> None:
        self._candidate_repository = candidate_repository
        self._generation_repository = generation_repository
        self._clock = clock
        self._video_generation_id_factory = video_generation_id_factory

    def execute(
        self,
        *,
        audio_version: int,
        video_version: int,
        stale_before: datetime,
        limit: int,
        renderer: str,
        video_format: str,
        width: int,
        height: int,
        fps: int,
    ) -> PrepareNewsVideoJobsResult:
        candidates = self._candidate_repository.list_candidates(
            audio_version=audio_version,
            video_version=video_version,
            stale_before=stale_before,
            limit=limit,
        )

        manager = ManageNewsVideoGeneration(
            repository=self._generation_repository,
            clock=self._clock,
            id_factory=self._video_generation_id_factory,
        )

        jobs: list[PreparedNewsVideoJob] = []

        for candidate in candidates:
            production = candidate.media_production
            audio = candidate.source_audio

            # A video must reference an exact, completed audio artifact.
            if audio.status is not NewsNarrationAudioStatus.GENERATED:
                continue

            if audio.media_production_id != production.media_production_id:
                continue

            if audio.audio_version != audio_version:
                continue

            if audio.storage_key is None or audio.content_sha256 is None:
                continue

            generation = manager.prepare(
                media_production_id=production.media_production_id,
                video_version=video_version,
                renderer=renderer,
                video_format=video_format,
                width=width,
                height=height,
                fps=fps,
                source_audio_generation_id=audio.audio_generation_id,
                source_audio_sha256=audio.content_sha256,
            )

            # A completed video must never be scheduled again.
            if generation.status is NewsVideoGenerationStatus.GENERATED:
                continue

            jobs.append(
                PreparedNewsVideoJob(
                    video_generation_id=generation.video_generation_id,
                    media_production_id=generation.media_production_id,
                    video_version=generation.video_version,
                    next_attempt_number=generation.attempt_count + 1,
                )
            )

        return PrepareNewsVideoJobsResult(
            candidate_count=len(candidates),
            prepared_count=len(jobs),
            jobs=tuple(jobs),
        )

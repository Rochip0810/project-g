from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from project_g.application.news.generate_news_script import (
    GenerateNewsScriptResult,
)
from project_g.domain.news.script_generation import (
    NewsScriptEvidenceSnapshot,
    NewsScriptGeneration,
)
from project_g.ports.repositories.news_script_generations import (
    NewsScriptGenerationAlreadyExistsError,
    NewsScriptGenerationNotFoundError,
    NewsScriptGenerationRepository,
)

Clock = Callable[[], datetime]
GenerationIdFactory = Callable[[], UUID]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NewsScriptGenerationRankingScoreMismatchError(RuntimeError):
    """Raised when an existing generation has another ranking score."""

    def __init__(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
        expected_ranking_score: int,
        actual_ranking_score: int,
    ) -> None:
        super().__init__(
            "Script generation ranking_score mismatch for "
            f"{intake_id}/{generation_version}: "
            f"existing={expected_ranking_score}, "
            f"requested={actual_ranking_score}"
        )
        self.intake_id = intake_id
        self.generation_version = generation_version
        self.expected_ranking_score = expected_ranking_score
        self.actual_ranking_score = actual_ranking_score


class ManageNewsScriptGeneration:
    def __init__(
        self,
        *,
        repository: NewsScriptGenerationRepository,
        clock: Clock = _utc_now,
        generation_id_factory: GenerationIdFactory = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._generation_id_factory = generation_id_factory

    def prepare(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
        ranking_score: int,
    ) -> NewsScriptGeneration:
        existing = self._repository.get_by_intake_version(
            intake_id=intake_id,
            generation_version=generation_version,
        )

        if existing is not None:
            return self._validate_ranking_score(
                existing,
                requested_ranking_score=ranking_score,
            )

        generation = NewsScriptGeneration.pending(
            generation_id=self._generation_id_factory(),
            intake_id=intake_id,
            generation_version=generation_version,
            ranking_score=ranking_score,
            created_at=self._clock(),
        )

        try:
            return self._repository.add(generation)
        except NewsScriptGenerationAlreadyExistsError:
            existing = self._repository.get_by_intake_version(
                intake_id=intake_id,
                generation_version=generation_version,
            )

            if existing is None:
                raise

            return self._validate_ranking_score(
                existing,
                requested_ranking_score=ranking_score,
            )

    def claim(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
        stale_after_seconds: int | None = None,
    ) -> NewsScriptGeneration | None:
        started_at = self._clock()

        stale_before = None

        if stale_after_seconds is not None:
            if stale_after_seconds < 1:
                raise ValueError("stale_after_seconds must be at least 1")

            stale_before = started_at - timedelta(seconds=stale_after_seconds)

        return self._repository.claim_by_intake_version(
            intake_id=intake_id,
            generation_version=generation_version,
            started_at=started_at,
            stale_before=stale_before,
        )

    def record_generated(
        self,
        *,
        generation_id: UUID,
        result: GenerateNewsScriptResult,
    ) -> NewsScriptGeneration:
        generation = self._get_generation(generation_id)

        evidence_snapshot = tuple(
            NewsScriptEvidenceSnapshot(
                text=fact.text,
                source_id=fact.source_id,
                source_url=fact.source_url,
                competition_level=fact.competition_level,
                role=fact.role,
            )
            for fact in result.background_facts
        )

        generated = generation.record_generated(
            hook=result.script.hook,
            main_narration=result.script.main_narration,
            project_g_comment=result.script.project_g_comment,
            closing=result.script.closing,
            full_narration=result.script.full_narration,
            evidence_snapshot=evidence_snapshot,
            completed_at=self._clock(),
        )

        return self._repository.update(generated)

    def mark_failed(
        self,
        *,
        generation_id: UUID,
        reason: str,
    ) -> NewsScriptGeneration:
        generation = self._get_generation(generation_id)

        failed = generation.mark_failed(
            reason=reason,
            completed_at=self._clock(),
        )

        return self._repository.update(failed)

    def _get_generation(
        self,
        generation_id: UUID,
    ) -> NewsScriptGeneration:
        generation = self._repository.get_by_generation_id(generation_id)

        if generation is None:
            raise NewsScriptGenerationNotFoundError(generation_id)

        return generation

    @staticmethod
    def _validate_ranking_score(
        generation: NewsScriptGeneration,
        *,
        requested_ranking_score: int,
    ) -> NewsScriptGeneration:
        if generation.ranking_score != requested_ranking_score:
            raise NewsScriptGenerationRankingScoreMismatchError(
                intake_id=generation.intake_id,
                generation_version=generation.generation_version,
                expected_ranking_score=generation.ranking_score,
                actual_ranking_score=requested_ranking_score,
            )

        return generation

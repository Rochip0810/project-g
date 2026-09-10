from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from project_g.domain.news.ranking import RankedNewsCandidate
from project_g.domain.news.script_generation import (
    NewsScriptGeneration,
    NewsScriptGenerationStatus,
)


class NewsScriptGenerationLookup(Protocol):
    def get_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
    ) -> NewsScriptGeneration | None: ...


@dataclass(frozen=True, slots=True)
class NewsScriptEnqueueCandidate:
    intake_id: UUID
    generation_version: int
    ranking_score: int


class SelectNewsScriptEnqueueCandidates:
    def __init__(
        self,
        *,
        repository: NewsScriptGenerationLookup,
    ) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        rankings: list[RankedNewsCandidate],
        generation_version: int = 1,
        min_ranking_score: int = 70,
        limit: int = 5,
    ) -> list[NewsScriptEnqueueCandidate]:
        if generation_version < 1:
            raise ValueError("generation_version must be at least 1")

        if not 0 <= min_ranking_score <= 100:
            raise ValueError("min_ranking_score must be between 0 and 100")

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        selected: list[NewsScriptEnqueueCandidate] = []

        for ranking in rankings:
            if ranking.ranking_score < min_ranking_score:
                continue

            if ranking.freshness_score <= 0:
                continue

            generation = self._repository.get_by_intake_version(
                intake_id=ranking.intake_id,
                generation_version=generation_version,
            )

            if generation is None:
                selected.append(
                    NewsScriptEnqueueCandidate(
                        intake_id=ranking.intake_id,
                        generation_version=generation_version,
                        ranking_score=ranking.ranking_score,
                    )
                )
            elif generation.status in {
                NewsScriptGenerationStatus.PENDING,
                NewsScriptGenerationStatus.FAILED,
            }:
                selected.append(
                    NewsScriptEnqueueCandidate(
                        intake_id=ranking.intake_id,
                        generation_version=generation_version,
                        ranking_score=generation.ranking_score,
                    )
                )

            if len(selected) >= limit:
                break

        return selected

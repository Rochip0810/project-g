from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from project_g.domain.news.media_production import (
    NewsMediaProduction,
)
from project_g.domain.news.script_generation import (
    NewsScriptGenerationStatus,
)
from project_g.ports.repositories.news_media_intake_candidates import (
    NewsMediaIntakeCandidateRepository,
)
from project_g.ports.repositories.news_media_productions import (
    NewsMediaProductionAlreadyExistsError,
    NewsMediaProductionRepository,
)


@dataclass(frozen=True, slots=True)
class CreateMediaProductionIntakesResult:
    candidate_count: int
    created_count: int
    duplicate_count: int
    created: tuple[NewsMediaProduction, ...]


class CreateMediaProductionIntakes:
    def __init__(
        self,
        *,
        candidate_repository: NewsMediaIntakeCandidateRepository,
        media_repository: NewsMediaProductionRepository,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._candidate_repository = candidate_repository
        self._media_repository = media_repository
        self._id_factory = id_factory

    def execute(
        self,
        *,
        media_version: int,
        limit: int,
        created_at: datetime,
    ) -> CreateMediaProductionIntakesResult:
        if media_version < 1:
            raise ValueError("media_version must be at least 1")

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        candidates = self._candidate_repository.list_candidates(
            media_version=media_version,
            limit=limit,
        )

        created: list[NewsMediaProduction] = []
        duplicate_count = 0

        for generation in candidates:
            if generation.status is not NewsScriptGenerationStatus.GENERATED:
                continue

            production = NewsMediaProduction.pending(
                media_production_id=self._id_factory(),
                script_generation_id=generation.generation_id,
                media_version=media_version,
                created_at=created_at,
            )

            try:
                stored = self._media_repository.add(production)
            except NewsMediaProductionAlreadyExistsError:
                duplicate_count += 1
                continue

            created.append(stored)

        return CreateMediaProductionIntakesResult(
            candidate_count=len(candidates),
            created_count=len(created),
            duplicate_count=duplicate_count,
            created=tuple(created),
        )

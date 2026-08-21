from datetime import datetime

from project_g.domain.news.ranking import (
    RankedNewsCandidate,
    rank_news_candidates,
)
from project_g.ports.repositories.news_ranking_candidates import (
    NewsRankingCandidateRepository,
)


class InvalidNewsRankingLimitError(ValueError):
    pass


class RankNewsCandidates:
    def __init__(
        self,
        repository: NewsRankingCandidateRepository,
    ) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        now: datetime,
        limit: int = 5,
    ) -> list[RankedNewsCandidate]:
        if not 1 <= limit <= 50:
            raise InvalidNewsRankingLimitError("limit must be between 1 and 50")

        candidates = self._repository.list_eligible_candidates()

        ranked = rank_news_candidates(
            candidates,
            now=now,
        )

        return ranked[:limit]

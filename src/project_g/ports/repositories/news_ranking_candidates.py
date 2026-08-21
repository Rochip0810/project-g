from typing import Protocol

from project_g.domain.news.ranking import (
    NewsRankingCandidate,
)


class NewsRankingCandidateRepository(Protocol):
    def list_eligible_candidates(
        self,
    ) -> list[NewsRankingCandidate]:
        """Return news items eligible for Project G ranking."""
        ...

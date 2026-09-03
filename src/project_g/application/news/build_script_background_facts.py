from datetime import datetime, timedelta
from uuid import UUID

from project_g.ports.news_context import (
    NewsContextSelector,
    NewsContextSelectorInput,
)
from project_g.ports.news_script import NewsScriptBackgroundFact
from project_g.ports.repositories.recent_news_context import (
    RecentNewsContextRepository,
)


class BuildNewsScriptBackgroundFacts:
    def __init__(
        self,
        *,
        repository: RecentNewsContextRepository,
        selector: NewsContextSelector,
    ) -> None:
        self._repository = repository
        self._selector = selector

    def execute(
        self,
        *,
        target_intake_id: UUID,
        target_title: str,
        target_description: str | None,
        now: datetime,
        lookback_days: int = 14,
        candidate_limit: int = 50,
    ) -> tuple[NewsScriptBackgroundFact, ...]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")

        if not 1 <= lookback_days <= 30:
            raise ValueError("lookback_days must be between 1 and 30")

        if not 1 <= candidate_limit <= 100:
            raise ValueError("candidate_limit must be between 1 and 100")

        candidates = self._repository.list_recent_context(
            exclude_intake_id=target_intake_id,
            published_since=now - timedelta(days=lookback_days),
            published_until=now,
            limit=candidate_limit,
        )

        if not candidates:
            return ()

        selected = self._selector.select(
            NewsContextSelectorInput(
                target_title=target_title,
                target_description=target_description,
                candidates=tuple(candidates),
            )
        )

        return tuple(
            NewsScriptBackgroundFact(
                text=fact.text,
                source_id=fact.source_id,
                source_url=fact.source_url,
                competition_level=fact.competition_level,
                role=fact.role,
            )
            for fact in selected.facts
        )

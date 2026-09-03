from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.build_script_background_facts import (
    BuildNewsScriptBackgroundFacts,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.recent_context import RecentNewsContextItem
from project_g.ports.news_context import (
    NewsContextSelectedFact,
    NewsContextSelectorInput,
    NewsContextSelectorResult,
)

_NOW = datetime(
    2026,
    8,
    29,
    9,
    0,
    tzinfo=UTC,
)

_TARGET_ID = UUID("00000000-0000-0000-0000-000000000001")


def _candidate() -> RecentNewsContextItem:
    return RecentNewsContextItem(
        intake_id=UUID("00000000-0000-0000-0000-000000000002"),
        source_id="hochi_giants_articles",
        canonical_url="https://hochi.news/articles/context",
        title="則本昂大が2軍戦で登板",
        description="5回を投げて3失点だった。",
        published_at=_NOW - timedelta(days=1),
        competition_level=CompetitionLevel.FARM,
    )


class FakeRecentNewsContextRepository:
    def __init__(
        self,
        items: list[RecentNewsContextItem],
    ) -> None:
        self.items = items
        self.exclude_intake_id: UUID | None = None
        self.published_since: datetime | None = None
        self.published_until: datetime | None = None
        self.limit: int | None = None

    def list_recent_context(
        self,
        *,
        exclude_intake_id: UUID,
        published_since: datetime,
        published_until: datetime,
        limit: int = 50,
    ) -> list[RecentNewsContextItem]:
        self.exclude_intake_id = exclude_intake_id
        self.published_since = published_since
        self.published_until = published_until
        self.limit = limit

        return self.items


class FakeNewsContextSelector:
    def __init__(
        self,
        result: NewsContextSelectorResult,
    ) -> None:
        self.result = result
        self.input_data: NewsContextSelectorInput | None = None
        self.call_count = 0

    def select(
        self,
        input_data: NewsContextSelectorInput,
    ) -> NewsContextSelectorResult:
        self.call_count += 1
        self.input_data = input_data

        return self.result


def test_service_builds_script_background_facts() -> None:
    candidate = _candidate()

    repository = FakeRecentNewsContextRepository([candidate])

    selector = FakeNewsContextSelector(
        NewsContextSelectorResult(
            facts=(
                NewsContextSelectedFact(
                    text="直近の2軍戦では5回3失点だった。",
                    source_intake_id=candidate.intake_id,
                    source_id=candidate.source_id,
                    source_url=candidate.canonical_url,
                    competition_level=candidate.competition_level,
                ),
            )
        )
    )

    service = BuildNewsScriptBackgroundFacts(
        repository=repository,
        selector=selector,
    )

    facts = service.execute(
        target_intake_id=_TARGET_ID,
        target_title="則本昂大が1軍に合流",
        target_description="試合前練習から1軍に合流した。",
        now=_NOW,
    )

    assert repository.exclude_intake_id == _TARGET_ID
    assert repository.published_since == (_NOW - timedelta(days=14))
    assert repository.published_until == _NOW
    assert repository.limit == 50

    assert selector.input_data is not None
    assert selector.input_data.target_title == ("則本昂大が1軍に合流")
    assert selector.input_data.target_description == ("試合前練習から1軍に合流した。")
    assert selector.input_data.candidates == (candidate,)

    assert len(facts) == 1
    assert facts[0].text == ("直近の2軍戦では5回3失点だった。")
    assert facts[0].source_id == "hochi_giants_articles"
    assert facts[0].source_url == ("https://hochi.news/articles/context")


def test_service_skips_selector_when_no_candidates() -> None:
    repository = FakeRecentNewsContextRepository([])

    selector = FakeNewsContextSelector(
        NewsContextSelectorResult(
            facts=(),
        )
    )

    service = BuildNewsScriptBackgroundFacts(
        repository=repository,
        selector=selector,
    )

    facts = service.execute(
        target_intake_id=_TARGET_ID,
        target_title="Target",
        target_description=None,
        now=_NOW,
    )

    assert facts == ()
    assert selector.call_count == 0


@pytest.mark.parametrize(
    (
        "now",
        "lookback_days",
        "candidate_limit",
        "message",
    ),
    [
        (
            datetime(2026, 8, 29, 9, 0),
            14,
            50,
            "now must be timezone-aware",
        ),
        (
            _NOW,
            0,
            50,
            "lookback_days must be between 1 and 30",
        ),
        (
            _NOW,
            31,
            50,
            "lookback_days must be between 1 and 30",
        ),
        (
            _NOW,
            14,
            0,
            "candidate_limit must be between 1 and 100",
        ),
        (
            _NOW,
            14,
            101,
            "candidate_limit must be between 1 and 100",
        ),
    ],
)
def test_service_rejects_invalid_configuration(
    now: datetime,
    lookback_days: int,
    candidate_limit: int,
    message: str,
) -> None:
    service = BuildNewsScriptBackgroundFacts(
        repository=FakeRecentNewsContextRepository([]),
        selector=FakeNewsContextSelector(
            NewsContextSelectorResult(
                facts=(),
            )
        ),
    )

    with pytest.raises(
        ValueError,
        match=message,
    ):
        service.execute(
            target_intake_id=_TARGET_ID,
            target_title="Target",
            target_description=None,
            now=now,
            lookback_days=lookback_days,
            candidate_limit=candidate_limit,
        )

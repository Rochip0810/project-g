from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.domain.news.ranking import (
    NewsRankingCandidate,
    calculate_freshness_score,
    calculate_ranking_score,
    rank_news_candidates,
)

_NOW = datetime(
    2026,
    8,
    21,
    12,
    0,
    tzinfo=UTC,
)


@pytest.mark.parametrize(
    ("hours_old", "expected"),
    [
        (0, 100),
        (2, 100),
        (3, 90),
        (6, 90),
        (7, 75),
        (12, 75),
        (13, 60),
        (24, 60),
        (25, 30),
        (48, 30),
        (49, 0),
    ],
)
def test_freshness_policy(
    hours_old: int,
    expected: int,
) -> None:
    published_at = _NOW - timedelta(hours=hours_old)

    assert (
        calculate_freshness_score(
            published_at,
            now=_NOW,
        )
        == expected
    )


def test_unknown_published_at_has_zero_freshness() -> None:
    assert (
        calculate_freshness_score(
            None,
            now=_NOW,
        )
        == 0
    )


def test_future_publication_is_treated_as_age_zero() -> None:
    published_at = _NOW + timedelta(hours=3)

    assert (
        calculate_freshness_score(
            published_at,
            now=_NOW,
        )
        == 100
    )


def test_weighted_ranking_score() -> None:
    assert (
        calculate_ranking_score(
            relevance_score=90,
            priority_score=80,
            freshness_score=100,
        )
        == 86
    )


def test_priority_is_dominant_signal() -> None:
    high_priority = NewsRankingCandidate(
        intake_id=UUID("00000000-0000-0000-0000-000000000001"),
        title="High priority",
        published_at=_NOW - timedelta(hours=5),
        relevance_score=80,
        priority_score=95,
    )
    lower_priority = NewsRankingCandidate(
        intake_id=UUID("00000000-0000-0000-0000-000000000002"),
        title="Lower priority",
        published_at=_NOW,
        relevance_score=100,
        priority_score=70,
    )

    ranked = rank_news_candidates(
        [
            lower_priority,
            high_priority,
        ],
        now=_NOW,
    )

    assert ranked[0].intake_id == high_priority.intake_id


def test_ranking_is_deterministic_on_ties() -> None:
    first = NewsRankingCandidate(
        intake_id=UUID("00000000-0000-0000-0000-000000000001"),
        title="First",
        published_at=_NOW,
        relevance_score=90,
        priority_score=90,
    )
    second = NewsRankingCandidate(
        intake_id=UUID("00000000-0000-0000-0000-000000000002"),
        title="Second",
        published_at=_NOW,
        relevance_score=90,
        priority_score=90,
    )

    ranked = rank_news_candidates(
        [
            second,
            first,
        ],
        now=_NOW,
    )

    assert ranked[0].intake_id == first.intake_id

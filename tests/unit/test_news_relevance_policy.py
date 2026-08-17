import pytest

from project_g.application.news.relevance_policy import (
    decide_news_relevance,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100, NewsRelevanceDecision.ACCEPTED),
        (70, NewsRelevanceDecision.ACCEPTED),
        (69, NewsRelevanceDecision.REVIEW),
        (40, NewsRelevanceDecision.REVIEW),
        (39, NewsRelevanceDecision.REJECTED),
        (0, NewsRelevanceDecision.REJECTED),
    ],
)
def test_relevance_score_maps_to_decision(
    score: int,
    expected: NewsRelevanceDecision,
) -> None:
    assert decide_news_relevance(score) is expected


@pytest.mark.parametrize(
    "score",
    [-1, 101],
)
def test_invalid_relevance_score_is_rejected(
    score: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="between 0 and 100",
    ):
        decide_news_relevance(score)

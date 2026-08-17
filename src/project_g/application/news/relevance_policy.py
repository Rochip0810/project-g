from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
)

_ACCEPTED_MIN_SCORE = 70
_REVIEW_MIN_SCORE = 40


def decide_news_relevance(
    relevance_score: int,
) -> NewsRelevanceDecision:
    if not 0 <= relevance_score <= 100:
        raise ValueError("relevance_score must be between 0 and 100")

    if relevance_score >= _ACCEPTED_MIN_SCORE:
        return NewsRelevanceDecision.ACCEPTED

    if relevance_score >= _REVIEW_MIN_SCORE:
        return NewsRelevanceDecision.REVIEW

    return NewsRelevanceDecision.REJECTED

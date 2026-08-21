from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NewsRankingCandidate:
    intake_id: UUID
    title: str
    published_at: datetime | None
    relevance_score: int
    priority_score: int


@dataclass(frozen=True, slots=True)
class RankedNewsCandidate:
    intake_id: UUID
    title: str
    published_at: datetime | None
    relevance_score: int
    priority_score: int
    freshness_score: int
    ranking_score: int


def calculate_freshness_score(
    published_at: datetime | None,
    *,
    now: datetime,
) -> int:
    if published_at is None:
        return 0

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    if published_at.tzinfo is None or published_at.utcoffset() is None:
        raise ValueError("published_at must be timezone-aware")

    now_utc = now.astimezone(UTC)
    published_utc = published_at.astimezone(UTC)

    age_seconds = max(
        0.0,
        (now_utc - published_utc).total_seconds(),
    )
    age_hours = age_seconds / 3600

    if age_hours <= 2:
        return 100
    if age_hours <= 6:
        return 90
    if age_hours <= 12:
        return 75
    if age_hours <= 24:
        return 60
    if age_hours <= 48:
        return 30

    return 0


def calculate_ranking_score(
    *,
    relevance_score: int,
    priority_score: int,
    freshness_score: int,
) -> int:
    for name, score in (
        ("relevance_score", relevance_score),
        ("priority_score", priority_score),
        ("freshness_score", freshness_score),
    ):
        if not 0 <= score <= 100:
            raise ValueError(f"{name} must be between 0 and 100")

    weighted_total = relevance_score * 15 + priority_score * 65 + freshness_score * 20

    return (weighted_total + 50) // 100


def rank_news_candidates(
    candidates: list[NewsRankingCandidate],
    *,
    now: datetime,
) -> list[RankedNewsCandidate]:
    ranked = [
        RankedNewsCandidate(
            intake_id=candidate.intake_id,
            title=candidate.title,
            published_at=candidate.published_at,
            relevance_score=candidate.relevance_score,
            priority_score=candidate.priority_score,
            freshness_score=calculate_freshness_score(
                candidate.published_at,
                now=now,
            ),
            ranking_score=calculate_ranking_score(
                relevance_score=candidate.relevance_score,
                priority_score=candidate.priority_score,
                freshness_score=calculate_freshness_score(
                    candidate.published_at,
                    now=now,
                ),
            ),
        )
        for candidate in candidates
    ]

    return sorted(
        ranked,
        key=lambda candidate: (
            -candidate.ranking_score,
            -candidate.priority_score,
            -(
                candidate.published_at.timestamp()
                if candidate.published_at is not None
                else float("-inf")
            ),
            str(candidate.intake_id),
        ),
    )

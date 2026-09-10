from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.select_news_script_enqueue_candidates import (
    NewsScriptEnqueueCandidate,
    SelectNewsScriptEnqueueCandidates,
)
from project_g.domain.news.ranking import RankedNewsCandidate
from project_g.domain.news.script_generation import (
    NewsScriptGeneration,
)

_NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

_NEW_ID = UUID("00000000-0000-0000-0000-000000000001")
_FAILED_ID = UUID("00000000-0000-0000-0000-000000000002")
_GENERATED_ID = UUID("00000000-0000-0000-0000-000000000003")
_GENERATING_ID = UUID("00000000-0000-0000-0000-000000000004")
_LOW_SCORE_ID = UUID("00000000-0000-0000-0000-000000000005")
_STALE_ID = UUID("00000000-0000-0000-0000-000000000006")


class FakeGenerationRepository:
    def __init__(
        self,
        generations: dict[UUID, NewsScriptGeneration],
    ) -> None:
        self._generations = generations

    def get_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
    ) -> NewsScriptGeneration | None:
        assert generation_version == 1
        return self._generations.get(intake_id)


def _ranked(
    intake_id: UUID,
    *,
    ranking_score: int,
    freshness_score: int,
) -> RankedNewsCandidate:
    return RankedNewsCandidate(
        intake_id=intake_id,
        title=f"News {intake_id}",
        published_at=_NOW - timedelta(hours=1),
        relevance_score=90,
        priority_score=80,
        freshness_score=freshness_score,
        ranking_score=ranking_score,
    )


def _pending(
    intake_id: UUID,
    *,
    ranking_score: int,
) -> NewsScriptGeneration:
    return NewsScriptGeneration.pending(
        generation_id=UUID(f"10000000-0000-0000-0000-{intake_id.int:012d}"),
        intake_id=intake_id,
        generation_version=1,
        ranking_score=ranking_score,
        created_at=_NOW - timedelta(minutes=10),
    )


def test_selects_new_and_failed_candidates_and_preserves_persisted_score() -> None:
    failed = (
        _pending(_FAILED_ID, ranking_score=91)
        .start(started_at=_NOW - timedelta(minutes=9))
        .mark_failed(
            reason="RuntimeError: news script generation failed",
            completed_at=_NOW - timedelta(minutes=8),
        )
    )

    generated = (
        _pending(_GENERATED_ID, ranking_score=95)
        .start(started_at=_NOW - timedelta(minutes=9))
        .record_generated(
            hook="hook",
            main_narration="main",
            project_g_comment="comment",
            closing="closing",
            full_narration="full",
            evidence_snapshot=(),
            completed_at=_NOW - timedelta(minutes=8),
        )
    )

    generating = _pending(
        _GENERATING_ID,
        ranking_score=93,
    ).start(
        started_at=_NOW - timedelta(minutes=1),
    )

    repository = FakeGenerationRepository(
        {
            _FAILED_ID: failed,
            _GENERATED_ID: generated,
            _GENERATING_ID: generating,
        }
    )

    service = SelectNewsScriptEnqueueCandidates(
        repository=repository,
    )

    result = service.execute(
        rankings=[
            _ranked(
                _GENERATED_ID,
                ranking_score=95,
                freshness_score=100,
            ),
            _ranked(
                _GENERATING_ID,
                ranking_score=93,
                freshness_score=100,
            ),
            _ranked(
                _FAILED_ID,
                ranking_score=88,
                freshness_score=90,
            ),
            _ranked(
                _NEW_ID,
                ranking_score=85,
                freshness_score=90,
            ),
            _ranked(
                _LOW_SCORE_ID,
                ranking_score=69,
                freshness_score=100,
            ),
            _ranked(
                _STALE_ID,
                ranking_score=90,
                freshness_score=0,
            ),
        ],
        generation_version=1,
        min_ranking_score=70,
        limit=5,
    )

    assert result == [
        NewsScriptEnqueueCandidate(
            intake_id=_FAILED_ID,
            generation_version=1,
            ranking_score=91,
        ),
        NewsScriptEnqueueCandidate(
            intake_id=_NEW_ID,
            generation_version=1,
            ranking_score=85,
        ),
    ]


@pytest.mark.parametrize(
    ("generation_version", "min_ranking_score", "limit"),
    [
        (0, 70, 5),
        (1, -1, 5),
        (1, 101, 5),
        (1, 70, 0),
        (1, 70, 51),
    ],
)
def test_rejects_invalid_selection_settings(
    generation_version: int,
    min_ranking_score: int,
    limit: int,
) -> None:
    service = SelectNewsScriptEnqueueCandidates(
        repository=FakeGenerationRepository({}),
    )

    with pytest.raises(ValueError):
        service.execute(
            rankings=[],
            generation_version=generation_version,
            min_ranking_score=min_ranking_score,
            limit=limit,
        )

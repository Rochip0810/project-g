from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from project_g.application.news.select_news_script_enqueue_candidates import (
    SelectNewsScriptEnqueueCandidates,
)
from project_g.domain.news.ranking import RankedNewsCandidate
from project_g.domain.news.script_generation import (
    NewsScriptGenerationStatus,
)
from project_g.infrastructure.database.models.news_script_generation import (
    NewsScriptGenerationRecord,
)
from project_g.infrastructure.database.repositories.news_script_generations import (
    SqlAlchemyNewsScriptGenerationRepository,
)

_FAILED_ID = UUID("00000000-0000-0000-0000-000000000101")
_PENDING_ID = UUID("00000000-0000-0000-0000-000000000102")
_NEW_ID = UUID("00000000-0000-0000-0000-000000000103")
_STALE_ID = UUID("00000000-0000-0000-0000-000000000104")

_NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def migrated_session(
    alembic_config: AlembicConfig,
    database_engine: Engine,
) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session
        session.rollback()


def _generation_record(
    *,
    intake_id: UUID,
    status: NewsScriptGenerationStatus,
    ranking_score: int,
    attempt_count: int,
    failure_reason: str | None,
) -> NewsScriptGenerationRecord:
    record = NewsScriptGenerationRecord()

    record.generation_id = uuid4()
    record.intake_id = intake_id
    record.generation_version = 1
    record.status = status.value
    record.ranking_score = ranking_score
    record.attempt_count = attempt_count

    record.failure_reason = failure_reason

    record.hook = None
    record.main_narration = None
    record.project_g_comment = None
    record.closing = None
    record.full_narration = None
    record.evidence_snapshot = None

    record.created_at = _NOW
    record.started_at = _NOW if attempt_count > 0 else None
    record.completed_at = _NOW if status is NewsScriptGenerationStatus.FAILED else None
    record.updated_at = _NOW

    return record


def _ranking(
    *,
    intake_id: UUID,
    ranking_score: int,
    freshness_score: int,
) -> RankedNewsCandidate:
    return cast(
        RankedNewsCandidate,
        SimpleNamespace(
            intake_id=intake_id,
            ranking_score=ranking_score,
            freshness_score=freshness_score,
        ),
    )


def test_selects_script_candidates_using_persisted_generation_state(
    migrated_session: Session,
) -> None:
    migrated_session.add_all(
        [
            _generation_record(
                intake_id=_FAILED_ID,
                status=NewsScriptGenerationStatus.FAILED,
                ranking_score=91,
                attempt_count=1,
                failure_reason=("RuntimeError: news script generation failed"),
            ),
            _generation_record(
                intake_id=_PENDING_ID,
                status=NewsScriptGenerationStatus.PENDING,
                ranking_score=84,
                attempt_count=0,
                failure_reason=None,
            ),
        ]
    )
    migrated_session.flush()

    repository = SqlAlchemyNewsScriptGenerationRepository(
        migrated_session,
    )
    selector = SelectNewsScriptEnqueueCandidates(
        repository=repository,
    )

    candidates = selector.execute(
        rankings=[
            # Current ranking changed, but FAILED must preserve persisted 91.
            _ranking(
                intake_id=_FAILED_ID,
                ranking_score=88,
                freshness_score=100,
            ),
            # PENDING also keeps the score captured when generation was created.
            _ranking(
                intake_id=_PENDING_ID,
                ranking_score=90,
                freshness_score=100,
            ),
            # No generation yet: use current calculated score.
            _ranking(
                intake_id=_NEW_ID,
                ranking_score=83,
                freshness_score=100,
            ),
            # Old ranking must not be selected even with a high score.
            _ranking(
                intake_id=_STALE_ID,
                ranking_score=99,
                freshness_score=0,
            ),
        ],
        generation_version=1,
        min_ranking_score=70,
        limit=5,
    )

    assert [
        (
            candidate.intake_id,
            candidate.generation_version,
            candidate.ranking_score,
        )
        for candidate in candidates
    ] == [
        (_FAILED_ID, 1, 91),
        (_PENDING_ID, 1, 84),
        (_NEW_ID, 1, 83),
    ]

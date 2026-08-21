from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
    SourceType,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
    NewsPriorityStatus,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsPriorityAnalysisRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories import (
    NewsPriorityAnalysisAlreadyExistsError,
    NewsPriorityAnalysisNotFoundError,
)

_ANALYSIS_1_ID = UUID("4f69da49-a0a8-49f0-a5cc-e2fdb6b63211")
_ANALYSIS_2_ID = UUID("1774db77-9500-4113-b418-04400974533c")
_INTAKE_ID = UUID("629986fd-a25f-4fd9-9fe4-46eb8c9acbb2")
_CREATED_AT = datetime(
    2026,
    8,
    21,
    1,
    0,
    tzinfo=UTC,
)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)


@pytest.fixture
def migrated_session(
    alembic_config: Config,
    database_engine: Engine,
) -> Iterator[Session]:
    command.upgrade(
        alembic_config,
        "head",
    )

    factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session


def _source() -> NewsSource:
    return NewsSource(
        source_id="giants_official_news",
        name="Giants Official News",
        source_type=SourceType.WEBSITE,
        base_url="https://www.giants.jp/news/",
        is_official=True,
        status=SourceStatus.PAUSED,
        priority=100,
    )


def _intake() -> ManualNewsIntake:
    return ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="giants_official_news",
        submitted_url=("https://www.giants.jp/news/888888/"),
        canonical_url=("https://www.giants.jp/news/888888/"),
        submitted_at=_CREATED_AT,
    )


def _pending(
    analysis_id: UUID = _ANALYSIS_1_ID,
) -> NewsPriorityAnalysis:
    return NewsPriorityAnalysis.pending(
        analysis_id=analysis_id,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def _seed_source_and_intake(
    session: Session,
) -> None:
    SqlAlchemyNewsSourceRepository(session).add(_source())
    SqlAlchemyManualNewsIntakeRepository(session).add(_intake())


def test_repository_adds_and_retrieves_analysis(
    migrated_session: Session,
) -> None:
    _seed_source_and_intake(migrated_session)

    repository = SqlAlchemyNewsPriorityAnalysisRepository(migrated_session)
    analysis = _pending()

    stored = repository.add(analysis)
    migrated_session.commit()
    migrated_session.expire_all()

    assert stored == analysis
    assert repository.get_by_analysis_id(analysis.analysis_id) == analysis
    assert repository.get_by_intake_id(analysis.intake_id) == analysis


def test_repository_updates_analyzed_result(
    migrated_session: Session,
) -> None:
    _seed_source_and_intake(migrated_session)

    repository = SqlAlchemyNewsPriorityAnalysisRepository(migrated_session)

    pending = _pending()
    repository.add(pending)

    analyzed = pending.record_analyzed(
        priority_score=90,
        reason="High editorial value for Project G.",
        updated_at=_UPDATED_AT,
    )

    stored = repository.update(analyzed)
    migrated_session.commit()
    migrated_session.expire_all()

    loaded = repository.get_by_analysis_id(analyzed.analysis_id)

    assert stored.status is NewsPriorityStatus.ANALYZED
    assert stored.priority_score == 90
    assert stored.reason == "High editorial value for Project G."
    assert loaded == analyzed


def test_repository_rejects_duplicate_intake_analysis(
    migrated_session: Session,
) -> None:
    _seed_source_and_intake(migrated_session)

    repository = SqlAlchemyNewsPriorityAnalysisRepository(migrated_session)

    repository.add(_pending())

    with pytest.raises(NewsPriorityAnalysisAlreadyExistsError):
        repository.add(_pending(analysis_id=_ANALYSIS_2_ID))


def test_repository_update_rejects_unknown_analysis(
    migrated_session: Session,
) -> None:
    _seed_source_and_intake(migrated_session)

    repository = SqlAlchemyNewsPriorityAnalysisRepository(migrated_session)

    with pytest.raises(NewsPriorityAnalysisNotFoundError):
        repository.update(_pending())

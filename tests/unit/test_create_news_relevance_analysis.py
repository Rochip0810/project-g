from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.create_relevance_analysis import (
    CreateNewsRelevanceAnalysis,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
    NewsRelevanceStatus,
)
from project_g.ports.repositories.news_relevance_analyses import (
    NewsRelevanceAnalysisAlreadyExistsError,
    NewsRelevanceAnalysisNotFoundError,
)

_ANALYSIS_ID = UUID("f35293c1-1c1a-48d7-b52c-d8dfe434cc13")
_INTAKE_ID = UUID("070aff1d-d13f-4acb-9f33-69366bbab990")
_CREATED_AT = datetime(
    2026,
    8,
    12,
    13,
    0,
    tzinfo=UTC,
)


class FakeNewsRelevanceAnalysisRepository:
    def __init__(self) -> None:
        self._by_analysis_id: dict[
            UUID,
            NewsRelevanceAnalysis,
        ] = {}
        self._by_intake_id: dict[
            UUID,
            NewsRelevanceAnalysis,
        ] = {}
        self.added: list[NewsRelevanceAnalysis] = []

    def add(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> NewsRelevanceAnalysis:
        if analysis.intake_id in self._by_intake_id:
            raise NewsRelevanceAnalysisAlreadyExistsError(analysis.intake_id)

        self._by_analysis_id[analysis.analysis_id] = analysis
        self._by_intake_id[analysis.intake_id] = analysis
        self.added.append(analysis)

        return analysis

    def update(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> NewsRelevanceAnalysis:
        if analysis.analysis_id not in self._by_analysis_id:
            raise NewsRelevanceAnalysisNotFoundError(analysis.analysis_id)

        self._by_analysis_id[analysis.analysis_id] = analysis
        self._by_intake_id[analysis.intake_id] = analysis

        return analysis

    def get_by_analysis_id(
        self,
        analysis_id: UUID,
    ) -> NewsRelevanceAnalysis | None:
        return self._by_analysis_id.get(analysis_id)

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsRelevanceAnalysis | None:
        return self._by_intake_id.get(intake_id)


def _service(
    repository: FakeNewsRelevanceAnalysisRepository,
) -> CreateNewsRelevanceAnalysis:
    return CreateNewsRelevanceAnalysis(
        repository=repository,
        clock=lambda: _CREATED_AT,
        analysis_id_factory=lambda: _ANALYSIS_ID,
    )


def test_service_creates_pending_analysis() -> None:
    repository = FakeNewsRelevanceAnalysisRepository()

    analysis = _service(repository).execute(_INTAKE_ID)

    assert analysis.analysis_id == _ANALYSIS_ID
    assert analysis.intake_id == _INTAKE_ID
    assert analysis.status is NewsRelevanceStatus.PENDING
    assert analysis.relevance_score is None
    assert analysis.decision is None
    assert analysis.reason is None
    assert analysis.failure_reason is None
    assert analysis.created_at == _CREATED_AT
    assert analysis.updated_at == _CREATED_AT
    assert repository.added == [analysis]


def test_service_rejects_duplicate_intake_analysis() -> None:
    repository = FakeNewsRelevanceAnalysisRepository()
    service = _service(repository)

    first = service.execute(_INTAKE_ID)

    with pytest.raises(
        NewsRelevanceAnalysisAlreadyExistsError,
        match="already exists",
    ):
        service.execute(_INTAKE_ID)

    assert repository.added == [first]


def test_repository_returns_analysis_by_intake() -> None:
    repository = FakeNewsRelevanceAnalysisRepository()

    created = _service(repository).execute(_INTAKE_ID)

    assert repository.get_by_intake_id(_INTAKE_ID) == created
    assert repository.get_by_analysis_id(_ANALYSIS_ID) == created

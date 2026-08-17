from typing import Protocol
from uuid import UUID

from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
)


class NewsRelevanceAnalysisAlreadyExistsError(RuntimeError):
    """Raised when an intake already has a relevance analysis."""

    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Relevance analysis already exists for intake: {intake_id}")
        self.intake_id = intake_id


class NewsRelevanceAnalysisNotFoundError(RuntimeError):
    """Raised when a relevance analysis cannot be found."""

    def __init__(self, analysis_id: UUID) -> None:
        super().__init__(f"Relevance analysis was not found: {analysis_id}")
        self.analysis_id = analysis_id


class NewsRelevanceAnalysisRepository(Protocol):
    def add(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> NewsRelevanceAnalysis:
        """Store and return a new relevance analysis."""
        ...

    def update(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> NewsRelevanceAnalysis:
        """Update and return an existing relevance analysis."""
        ...

    def get_by_analysis_id(
        self,
        analysis_id: UUID,
    ) -> NewsRelevanceAnalysis | None:
        """Return a relevance analysis by its ID."""
        ...

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsRelevanceAnalysis | None:
        """Return the relevance analysis for an intake."""
        ...

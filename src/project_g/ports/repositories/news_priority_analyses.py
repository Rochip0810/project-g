from typing import Protocol
from uuid import UUID

from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
)


class NewsPriorityAnalysisAlreadyExistsError(RuntimeError):
    """Raised when an intake already has a priority analysis."""

    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Priority analysis already exists for intake: {intake_id}")
        self.intake_id = intake_id


class NewsPriorityAnalysisNotFoundError(RuntimeError):
    """Raised when a priority analysis cannot be found."""

    def __init__(self, analysis_id: UUID) -> None:
        super().__init__(f"Priority analysis was not found: {analysis_id}")
        self.analysis_id = analysis_id


class NewsPriorityAnalysisRepository(Protocol):
    def add(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> NewsPriorityAnalysis:
        """Store and return a new priority analysis."""
        ...

    def update(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> NewsPriorityAnalysis:
        """Update and return an existing priority analysis."""
        ...

    def get_by_analysis_id(
        self,
        analysis_id: UUID,
    ) -> NewsPriorityAnalysis | None:
        """Return a priority analysis by its ID."""
        ...

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsPriorityAnalysis | None:
        """Return the priority analysis for an intake."""
        ...

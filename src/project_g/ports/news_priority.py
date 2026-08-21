from dataclasses import dataclass
from typing import Protocol

from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
)


@dataclass(frozen=True, slots=True)
class NewsPriorityAnalyzerInput:
    source_id: str
    title: str
    description: str | None
    relevance_score: int
    relevance_decision: NewsRelevanceDecision


@dataclass(frozen=True, slots=True)
class NewsPriorityAnalyzerResult:
    priority_score: int
    reason: str


class NewsPriorityAnalyzer(Protocol):
    def analyze(
        self,
        input_data: NewsPriorityAnalyzerInput,
    ) -> NewsPriorityAnalyzerResult:
        """Assess the editorial priority of one Giants-related news item."""
        ...

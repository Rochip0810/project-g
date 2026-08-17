from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NewsRelevanceAnalyzerInput:
    source_id: str
    title: str
    description: str | None


@dataclass(frozen=True, slots=True)
class NewsRelevanceAnalyzerResult:
    relevance_score: int
    reason: str


class NewsRelevanceAnalyzer(Protocol):
    def analyze(
        self,
        input_data: NewsRelevanceAnalyzerInput,
    ) -> NewsRelevanceAnalyzerResult:
        """Assess how relevant one news item is to Project G."""
        ...

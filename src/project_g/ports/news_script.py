from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NewsScriptBackgroundFact:
    text: str
    source_id: str
    source_url: str


@dataclass(frozen=True, slots=True)
class NewsScriptGeneratorInput:
    intake_id: UUID
    source_id: str
    title: str
    description: str | None
    canonical_url: str
    relevance_score: int
    priority_score: int
    ranking_score: int
    background_facts: tuple[NewsScriptBackgroundFact, ...] = ()


@dataclass(frozen=True, slots=True)
class NewsScriptGeneratorResult:
    hook: str
    main_narration: str
    project_g_comment: str
    closing: str
    full_narration: str


class NewsScriptGenerator(Protocol):
    def generate(
        self,
        input_data: NewsScriptGeneratorInput,
    ) -> NewsScriptGeneratorResult:
        """Generate one Project G Shorts script."""
        ...

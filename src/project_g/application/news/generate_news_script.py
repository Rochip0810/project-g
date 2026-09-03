from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from project_g.ports.news_script import (
    NewsScriptBackgroundFact,
    NewsScriptGenerator,
    NewsScriptGeneratorInput,
    NewsScriptGeneratorResult,
)


class NewsScriptBackgroundFactsBuilder(Protocol):
    def execute(
        self,
        *,
        target_intake_id: UUID,
        target_title: str,
        target_description: str | None,
        now: datetime,
        lookback_days: int = 14,
        candidate_limit: int = 50,
    ) -> tuple[NewsScriptBackgroundFact, ...]:
        """Build verified background facts from recent news context."""
        ...


class AuthoritativeNewsScriptFactsProvider(Protocol):
    def collect(
        self,
        *,
        target_intake_id: UUID,
        target_title: str,
        target_description: str | None,
        target_canonical_url: str,
        published_until: datetime,
    ) -> tuple[NewsScriptBackgroundFact, ...]:
        """Collect additional verified facts from authoritative sources."""
        ...


def _deduplicate_background_facts(
    facts: tuple[NewsScriptBackgroundFact, ...],
) -> tuple[NewsScriptBackgroundFact, ...]:
    seen: set[NewsScriptBackgroundFact] = set()
    unique: list[NewsScriptBackgroundFact] = []

    for fact in facts:
        if fact in seen:
            continue

        seen.add(fact)
        unique.append(fact)

    return tuple(unique)


@dataclass(frozen=True, slots=True)
class GenerateNewsScriptInput:
    intake_id: UUID
    source_id: str
    title: str
    description: str | None
    canonical_url: str
    published_at: datetime
    relevance_score: int
    priority_score: int
    ranking_score: int


@dataclass(frozen=True, slots=True)
class GenerateNewsScriptResult:
    script: NewsScriptGeneratorResult
    background_facts: tuple[NewsScriptBackgroundFact, ...]


class GenerateNewsScript:
    def __init__(
        self,
        *,
        background_builder: NewsScriptBackgroundFactsBuilder,
        generator: NewsScriptGenerator,
        authoritative_facts_provider: AuthoritativeNewsScriptFactsProvider | None = None,
    ) -> None:
        self._background_builder = background_builder
        self._generator = generator
        self._authoritative_facts_provider = authoritative_facts_provider

    def execute(
        self,
        input_data: GenerateNewsScriptInput,
    ) -> GenerateNewsScriptResult:
        if input_data.published_at.tzinfo is None or input_data.published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")

        recent_facts = self._background_builder.execute(
            target_intake_id=input_data.intake_id,
            target_title=input_data.title,
            target_description=input_data.description,
            now=input_data.published_at,
        )

        authoritative_facts: tuple[
            NewsScriptBackgroundFact,
            ...,
        ] = ()

        if self._authoritative_facts_provider is not None:
            authoritative_facts = self._authoritative_facts_provider.collect(
                target_intake_id=input_data.intake_id,
                target_title=input_data.title,
                target_description=input_data.description,
                target_canonical_url=input_data.canonical_url,
                published_until=input_data.published_at,
            )

        background_facts = _deduplicate_background_facts(recent_facts + authoritative_facts)

        script = self._generator.generate(
            NewsScriptGeneratorInput(
                intake_id=input_data.intake_id,
                source_id=input_data.source_id,
                title=input_data.title,
                description=input_data.description,
                canonical_url=input_data.canonical_url,
                relevance_score=input_data.relevance_score,
                priority_score=input_data.priority_score,
                ranking_score=input_data.ranking_score,
                background_facts=background_facts,
            )
        )

        return GenerateNewsScriptResult(
            script=script,
            background_facts=background_facts,
        )

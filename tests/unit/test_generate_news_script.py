from datetime import UTC, datetime
from uuid import UUID

from project_g.application.news.generate_news_script import (
    GenerateNewsScript,
    GenerateNewsScriptInput,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.ports.news_script import (
    NewsScriptBackgroundFact,
    NewsScriptGeneratorInput,
    NewsScriptGeneratorResult,
)

_TARGET_ID = UUID("2c4c3406-7e28-4207-966e-2cd5dfb5e5e5")
_TARGET_PUBLISHED_AT = datetime(
    2026,
    8,
    22,
    0,
    47,
    tzinfo=UTC,
)


class FakeBackgroundBuilder:
    def __init__(
        self,
        facts: tuple[NewsScriptBackgroundFact, ...],
    ) -> None:
        self._facts = facts
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "target_intake_id": target_intake_id,
                "target_title": target_title,
                "target_description": target_description,
                "now": now,
                "lookback_days": lookback_days,
                "candidate_limit": candidate_limit,
            }
        )
        return self._facts


class FakeScriptGenerator:
    def __init__(self) -> None:
        self.inputs: list[NewsScriptGeneratorInput] = []

    def generate(
        self,
        input_data: NewsScriptGeneratorInput,
    ) -> NewsScriptGeneratorResult:
        self.inputs.append(input_data)

        return NewsScriptGeneratorResult(
            hook="Hook",
            main_narration="Main",
            project_g_comment="Comment",
            closing="Closing",
            full_narration=(
                "Hook\n\nMain\n\nここからはPROJECT Gの見解です。\n\nComment\n\nClosing"
            ),
            evidence_points=input_data.background_facts,
        )


def _input() -> GenerateNewsScriptInput:
    return GenerateNewsScriptInput(
        intake_id=_TARGET_ID,
        source_id="hochi_giants_articles",
        title="【巨人】則本昂大が１軍合流",
        description="則本昂大投手が１軍に合流した。",
        canonical_url=("https://hochi.news/articles/20260822-OHT1T51073.html"),
        published_at=_TARGET_PUBLISHED_AT,
        relevance_score=97,
        priority_score=91,
        ranking_score=94,
    )


def test_execute_uses_target_published_at_as_context_upper_bound() -> None:
    fact = NewsScriptBackgroundFact(
        text="Verified background fact",
        source_id="npb_official",
        source_url="https://npb.jp/example",
        competition_level=CompetitionLevel.FARM,
        role=EvidenceRole.TARGET,
    )

    background_builder = FakeBackgroundBuilder((fact,))
    generator = FakeScriptGenerator()

    service = GenerateNewsScript(
        background_builder=background_builder,
        generator=generator,
    )

    result = service.execute(_input())

    assert len(background_builder.calls) == 1
    assert background_builder.calls[0]["now"] == _TARGET_PUBLISHED_AT

    assert len(generator.inputs) == 1

    generator_input = generator.inputs[0]

    assert generator_input.intake_id == _TARGET_ID
    assert generator_input.background_facts == (fact,)
    assert generator_input.relevance_score == 97
    assert generator_input.priority_score == 91
    assert generator_input.ranking_score == 94

    assert result.background_facts == (fact,)
    assert result.script.evidence_points == (fact,)


def test_execute_generates_script_when_background_context_is_empty() -> None:
    background_builder = FakeBackgroundBuilder(())
    generator = FakeScriptGenerator()

    service = GenerateNewsScript(
        background_builder=background_builder,
        generator=generator,
    )

    result = service.execute(_input())

    assert len(generator.inputs) == 1
    assert generator.inputs[0].background_facts == ()
    assert result.background_facts == ()
    assert result.script.full_narration


def test_execute_rejects_naive_published_at() -> None:
    background_builder = FakeBackgroundBuilder(())
    generator = FakeScriptGenerator()

    service = GenerateNewsScript(
        background_builder=background_builder,
        generator=generator,
    )

    input_data = _input()
    naive_input = GenerateNewsScriptInput(
        intake_id=input_data.intake_id,
        source_id=input_data.source_id,
        title=input_data.title,
        description=input_data.description,
        canonical_url=input_data.canonical_url,
        published_at=datetime(
            2026,
            8,
            22,
            0,
            47,
        ),
        relevance_score=input_data.relevance_score,
        priority_score=input_data.priority_score,
        ranking_score=input_data.ranking_score,
    )

    try:
        service.execute(naive_input)
    except ValueError as error:
        assert str(error) == "published_at must be timezone-aware"
    else:
        raise AssertionError("Expected ValueError")

    assert background_builder.calls == []
    assert generator.inputs == []


def test_execute_preserves_comparison_evidence_role() -> None:
    target_fact = NewsScriptBackgroundFact(
        text="Target evidence",
        source_id="npb_official",
        source_url="https://npb.jp/target",
        competition_level=CompetitionLevel.FARM,
        role=EvidenceRole.TARGET,
    )
    comparison_fact = NewsScriptBackgroundFact(
        text="Comparison evidence",
        source_id="npb_official",
        source_url="https://npb.jp/comparison",
        competition_level=CompetitionLevel.FIRST_TEAM,
        role=EvidenceRole.COMPARISON,
    )

    background_builder = FakeBackgroundBuilder(
        (
            target_fact,
            comparison_fact,
        )
    )
    generator = FakeScriptGenerator()

    service = GenerateNewsScript(
        background_builder=background_builder,
        generator=generator,
    )

    result = service.execute(_input())

    assert len(generator.inputs) == 1

    generator_input = generator.inputs[0]

    assert generator_input.background_facts == (
        target_fact,
        comparison_fact,
    )
    assert generator_input.background_facts[1].role is EvidenceRole.COMPARISON
    assert generator_input.background_facts[1].competition_level is CompetitionLevel.FIRST_TEAM

    assert result.background_facts == (
        target_fact,
        comparison_fact,
    )


class FakeAuthoritativeFactsProvider:
    def __init__(
        self,
        facts: tuple[NewsScriptBackgroundFact, ...],
    ) -> None:
        self._facts = facts
        self.calls: list[dict[str, object]] = []

    def collect(
        self,
        *,
        target_intake_id: UUID,
        target_title: str,
        target_description: str | None,
        target_canonical_url: str,
        published_until: datetime,
    ) -> tuple[NewsScriptBackgroundFact, ...]:
        self.calls.append(
            {
                "target_intake_id": target_intake_id,
                "target_title": target_title,
                "target_description": target_description,
                "target_canonical_url": target_canonical_url,
                "published_until": published_until,
            }
        )
        return self._facts


def test_execute_adds_authoritative_verified_evidence() -> None:
    recent_fact = NewsScriptBackgroundFact(
        text="Recent context fact",
        source_id="hochi_giants_articles",
        source_url="https://hochi.news/example",
        role=EvidenceRole.TARGET,
    )
    authoritative_fact = NewsScriptBackgroundFact(
        text="Verified NPB comparison fact",
        source_id="npb_official",
        source_url="https://npb.jp/example",
        competition_level=CompetitionLevel.FIRST_TEAM,
        role=EvidenceRole.COMPARISON,
    )

    background_builder = FakeBackgroundBuilder((recent_fact,))
    authoritative_provider = FakeAuthoritativeFactsProvider((authoritative_fact,))
    generator = FakeScriptGenerator()

    service = GenerateNewsScript(
        background_builder=background_builder,
        authoritative_facts_provider=authoritative_provider,
        generator=generator,
    )

    result = service.execute(_input())

    assert len(authoritative_provider.calls) == 1
    assert authoritative_provider.calls[0]["published_until"] == _TARGET_PUBLISHED_AT

    assert len(generator.inputs) == 1
    assert generator.inputs[0].background_facts == (
        recent_fact,
        authoritative_fact,
    )

    assert result.background_facts == (
        recent_fact,
        authoritative_fact,
    )


def test_execute_deduplicates_identical_background_facts() -> None:
    duplicate_fact = NewsScriptBackgroundFact(
        text="Same verified fact",
        source_id="npb_official",
        source_url="https://npb.jp/same",
        competition_level=CompetitionLevel.FIRST_TEAM,
        role=EvidenceRole.TARGET,
    )

    background_builder = FakeBackgroundBuilder((duplicate_fact,))
    authoritative_provider = FakeAuthoritativeFactsProvider((duplicate_fact,))
    generator = FakeScriptGenerator()

    service = GenerateNewsScript(
        background_builder=background_builder,
        authoritative_facts_provider=authoritative_provider,
        generator=generator,
    )

    result = service.execute(_input())

    assert len(generator.inputs) == 1
    assert generator.inputs[0].background_facts == (duplicate_fact,)
    assert result.background_facts == (duplicate_fact,)


def test_execute_keeps_distinct_facts_from_same_source_url() -> None:
    source_url = "https://npb.jp/scores/2026/example/box.html"

    target_fact = NewsScriptBackgroundFact(
        text="則本の投球内容",
        source_id="npb_official",
        source_url=source_url,
        competition_level=CompetitionLevel.FARM,
        role=EvidenceRole.TARGET,
    )
    comparison_fact = NewsScriptBackgroundFact(
        text="堀田の投球内容",
        source_id="npb_official",
        source_url=source_url,
        competition_level=CompetitionLevel.FIRST_TEAM,
        role=EvidenceRole.COMPARISON,
    )

    background_builder = FakeBackgroundBuilder((target_fact,))
    authoritative_provider = FakeAuthoritativeFactsProvider((comparison_fact,))
    generator = FakeScriptGenerator()

    service = GenerateNewsScript(
        background_builder=background_builder,
        authoritative_facts_provider=authoritative_provider,
        generator=generator,
    )

    result = service.execute(_input())

    assert generator.inputs[0].background_facts == (
        target_fact,
        comparison_fact,
    )
    assert result.background_facts == (
        target_fact,
        comparison_fact,
    )

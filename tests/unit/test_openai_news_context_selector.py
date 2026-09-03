import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

import project_g.infrastructure.ai.openai_context as module
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.recent_context import RecentNewsContextItem
from project_g.infrastructure.ai.openai_context import (
    OpenAIContextFactOutput,
    OpenAIContextOutput,
    OpenAIContextResponseError,
    OpenAINewsContextSelector,
)
from project_g.ports.news_context import NewsContextSelectorInput


class FakeResponses:
    def __init__(
        self,
        output: OpenAIContextOutput | None,
    ) -> None:
        self.output = output
        self.kwargs: dict[str, object] | None = None
        self.call_count = 0

    def parse(
        self,
        **kwargs: object,
    ) -> SimpleNamespace:
        self.call_count += 1
        self.kwargs = kwargs

        return SimpleNamespace(
            output_parsed=self.output,
        )


class FakeOpenAIClient:
    def __init__(
        self,
        output: OpenAIContextOutput | None,
    ) -> None:
        self.responses = FakeResponses(output)


def _candidate(
    *,
    number: int,
    title: str,
    description: str | None,
) -> RecentNewsContextItem:
    return RecentNewsContextItem(
        intake_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        source_id="hochi_giants_articles",
        canonical_url=f"https://hochi.news/articles/{number}",
        title=title,
        description=description,
        published_at=datetime(
            2026,
            8,
            28,
            12,
            number,
            tzinfo=UTC,
        ),
        competition_level=CompetitionLevel.FARM,
    )


def _input() -> NewsContextSelectorInput:
    return NewsContextSelectorInput(
        target_title="則本昂大が1軍に合流",
        target_description="東京ドームでの試合前練習から1軍に合流した。",
        candidates=(
            _candidate(
                number=1,
                title="則本昂大が2軍戦で登板",
                description="5回を投げて3失点だった。",
            ),
            _candidate(
                number=2,
                title="岡本和真が本塁打",
                description="試合で本塁打を放った。",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("api_key", "model", "timeout_seconds", "message"),
    [
        (
            "",
            "test-model",
            30,
            "OpenAI API key must not be empty",
        ),
        (
            "test-key",
            "",
            30,
            "OpenAI model must not be empty",
        ),
        (
            "test-key",
            "test-model",
            0,
            "OpenAI timeout_seconds must be greater than zero",
        ),
    ],
)
def test_constructor_rejects_invalid_configuration(
    api_key: str,
    model: str,
    timeout_seconds: float,
    message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=message,
    ):
        OpenAINewsContextSelector(
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )


def test_selector_returns_empty_without_calling_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIContextOutput(
            facts=[],
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    selector = OpenAINewsContextSelector(
        api_key="test-key",
        model="test-model",
        timeout_seconds=30,
    )

    result = selector.select(
        NewsContextSelectorInput(
            target_title="Target",
            target_description=None,
            candidates=(),
        )
    )

    assert result.facts == ()
    assert fake_client.responses.call_count == 0


def test_selector_maps_selected_index_to_trusted_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIContextOutput(
            facts=[
                OpenAIContextFactOutput(
                    candidate_index=0,
                    role=EvidenceRole.TARGET,
                    fact="直近の2軍戦では5回3失点だった。",
                )
            ],
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    selector = OpenAINewsContextSelector(
        api_key="test-key",
        model="test-model",
        timeout_seconds=30,
    )

    result = selector.select(_input())

    assert len(result.facts) == 1

    fact = result.facts[0]

    assert fact.text == "直近の2軍戦では5回3失点だった。"
    assert fact.source_intake_id == UUID("00000000-0000-0000-0000-000000000001")
    assert fact.source_id == "hochi_giants_articles"
    assert fact.source_url == "https://hochi.news/articles/1"
    assert fact.competition_level is CompetitionLevel.FARM
    assert fact.role is EvidenceRole.TARGET


def test_selector_sends_only_candidate_index_not_provenance_to_model_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIContextOutput(
            facts=[],
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    selector = OpenAINewsContextSelector(
        api_key="test-key",
        model="test-model",
        timeout_seconds=30,
    )

    selector.select(_input())

    assert fake_client.responses.kwargs is not None

    payload = json.loads(str(fake_client.responses.kwargs["input"]))

    assert payload["target"] == {
        "title": "則本昂大が1軍に合流",
        "description": "東京ドームでの試合前練習から1軍に合流した。",
    }

    assert payload["candidates"][0]["candidate_index"] == 0
    assert payload["candidates"][0]["title"] == "則本昂大が2軍戦で登板"
    assert payload["candidates"][0]["competition_level"] == "farm"
    assert payload["candidates"][0]["description"] == "5回を投げて3失点だった。"

    assert fake_client.responses.kwargs["model"] == "test-model"
    assert fake_client.responses.kwargs["text_format"] is OpenAIContextOutput
    assert fake_client.responses.kwargs["reasoning"] == {
        "effort": "none",
    }
    assert fake_client.responses.kwargs["store"] is False

    instructions = str(fake_client.responses.kwargs["instructions"])

    assert "directly supported" in instructions
    assert "Do not use outside knowledge" in instructions
    assert "Do not output URLs or source names" in instructions
    assert "competing for a similar role" in instructions
    assert "opportunity-cost context" in instructions
    assert "does NOT need to mention the target player" in instructions
    assert "Selecting another player's factual performance is allowed" in instructions
    assert "Leave the editorial comparison and opinion to the Script AI" in instructions
    assert '"target"' in instructions
    assert '"comparison"' in instructions
    assert '"team_context"' in instructions
    assert "Role classification must not add opinions" in instructions


def test_selector_rejects_invalid_candidate_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIContextOutput(
            facts=[
                OpenAIContextFactOutput(
                    candidate_index=99,
                    role=EvidenceRole.TARGET,
                    fact="Invalid source fact.",
                )
            ],
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    selector = OpenAINewsContextSelector(
        api_key="test-key",
        model="test-model",
        timeout_seconds=30,
    )

    with pytest.raises(
        OpenAIContextResponseError,
        match="invalid context candidate index",
    ):
        selector.select(_input())


def test_selector_rejects_missing_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(None)

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    selector = OpenAINewsContextSelector(
        api_key="test-key",
        model="test-model",
        timeout_seconds=30,
    )

    with pytest.raises(
        OpenAIContextResponseError,
        match="no parsed context output",
    ):
        selector.select(_input())


def test_selector_deduplicates_identical_selected_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIContextOutput(
            facts=[
                OpenAIContextFactOutput(
                    candidate_index=0,
                    role=EvidenceRole.TARGET,
                    fact="5回3失点だった。",
                ),
                OpenAIContextFactOutput(
                    candidate_index=0,
                    role=EvidenceRole.TARGET,
                    fact="5回3失点だった。",
                ),
            ],
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    selector = OpenAINewsContextSelector(
        api_key="test-key",
        model="test-model",
        timeout_seconds=30,
    )

    result = selector.select(_input())

    assert len(result.facts) == 1


def test_selector_preserves_comparison_evidence_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIContextOutput(
            facts=[
                OpenAIContextFactOutput(
                    candidate_index=1,
                    role=EvidenceRole.COMPARISON,
                    fact="別の投手は直近の登板で好投した。",
                )
            ],
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    selector = OpenAINewsContextSelector(
        api_key="test-key",
        model="test-model",
        timeout_seconds=30,
    )

    result = selector.select(_input())

    assert len(result.facts) == 1
    assert result.facts[0].role is EvidenceRole.COMPARISON
    assert result.facts[0].source_intake_id == UUID("00000000-0000-0000-0000-000000000002")

from types import SimpleNamespace
from typing import Any

import pytest

import project_g.infrastructure.ai.openai_relevance as module
from project_g.infrastructure.ai.openai_relevance import (
    OpenAIRelevanceAnalyzer,
    OpenAIRelevanceOutput,
    OpenAIRelevanceResponseError,
)
from project_g.ports.news_relevance import (
    NewsRelevanceAnalyzerInput,
)


class FakeResponses:
    def __init__(
        self,
        output: OpenAIRelevanceOutput | None,
    ) -> None:
        self.output = output
        self.kwargs: dict[str, Any] | None = None

    def parse(
        self,
        **kwargs: Any,
    ) -> SimpleNamespace:
        self.kwargs = kwargs

        return SimpleNamespace(
            output_parsed=self.output,
        )


class FakeOpenAIClient:
    def __init__(
        self,
        output: OpenAIRelevanceOutput | None,
    ) -> None:
        self.responses = FakeResponses(output)


def _input() -> NewsRelevanceAnalyzerInput:
    return NewsRelevanceAnalyzerInput(
        source_id="hochi_giants_articles",
        title="【巨人】ダルベックが20号",
        description="巨人の試合に関する記事です。",
    )


def test_analyzer_returns_structured_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIRelevanceOutput(
            relevance_score=94,
            reason="巨人の一軍戦に直接関係する重要なニュースです。",
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    analyzer = OpenAIRelevanceAnalyzer(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    result = analyzer.analyze(_input())

    assert result.relevance_score == 94
    assert result.reason == "巨人の一軍戦に直接関係する重要なニュースです。"

    assert fake_client.responses.kwargs is not None
    assert fake_client.responses.kwargs["model"] == "gpt-5.6-luna"
    assert fake_client.responses.kwargs["text_format"] is OpenAIRelevanceOutput
    assert fake_client.responses.kwargs["store"] is False
    assert fake_client.responses.kwargs["timeout"] == 30


def test_analyzer_rejects_missing_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(None)

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    analyzer = OpenAIRelevanceAnalyzer(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    with pytest.raises(
        OpenAIRelevanceResponseError,
        match="no parsed relevance output",
    ):
        analyzer.analyze(_input())


@pytest.mark.parametrize(
    "score",
    [-1, 101],
)
def test_output_rejects_invalid_score(
    score: int,
) -> None:
    with pytest.raises(ValueError):
        OpenAIRelevanceOutput(
            relevance_score=score,
            reason="reason",
        )


def test_analyzer_rejects_empty_api_key() -> None:
    with pytest.raises(
        ValueError,
        match="API key",
    ):
        OpenAIRelevanceAnalyzer(
            api_key="",
            model="gpt-5.6-luna",
            timeout_seconds=30,
        )

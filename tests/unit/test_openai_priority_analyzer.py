import json
from types import SimpleNamespace
from typing import Any

import pytest

import project_g.infrastructure.ai.openai_priority as module
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
)
from project_g.infrastructure.ai.openai_priority import (
    OpenAIPriorityAnalyzer,
    OpenAIPriorityOutput,
    OpenAIPriorityResponseError,
)
from project_g.ports.news_priority import (
    NewsPriorityAnalyzerInput,
)


class FakeResponses:
    def __init__(
        self,
        output: OpenAIPriorityOutput | None,
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
        output: OpenAIPriorityOutput | None,
    ) -> None:
        self.responses = FakeResponses(output)


def _input() -> NewsPriorityAnalyzerInput:
    return NewsPriorityAnalyzerInput(
        source_id="hochi_giants_articles",
        title="【巨人】主力選手が決勝本塁打",
        description="巨人の試合で主力選手が活躍した。",
        relevance_score=95,
        relevance_decision=NewsRelevanceDecision.ACCEPTED,
    )


def test_analyzer_returns_structured_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIPriorityOutput(
            priority_score=92,
            reason="試合結果に直結する主力選手の活躍で、編集価値が高い。",
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    analyzer = OpenAIPriorityAnalyzer(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    result = analyzer.analyze(_input())

    assert result.priority_score == 92
    assert result.reason == "試合結果に直結する主力選手の活躍で、編集価値が高い。"

    assert fake_client.responses.kwargs is not None
    assert fake_client.responses.kwargs["model"] == "gpt-5.6-luna"
    assert fake_client.responses.kwargs["text_format"] is OpenAIPriorityOutput
    assert fake_client.responses.kwargs["reasoning"] == {"effort": "none"}
    assert fake_client.responses.kwargs["max_output_tokens"] == 300
    assert fake_client.responses.kwargs["store"] is False
    assert fake_client.responses.kwargs["timeout"] == 30


def test_analyzer_sends_only_allowed_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAIPriorityOutput(
            priority_score=80,
            reason="編集候補として価値がある。",
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    analyzer = OpenAIPriorityAnalyzer(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    analyzer.analyze(_input())

    assert fake_client.responses.kwargs is not None

    payload = json.loads(fake_client.responses.kwargs["input"])

    assert payload == {
        "source_id": "hochi_giants_articles",
        "title": "【巨人】主力選手が決勝本塁打",
        "description": "巨人の試合で主力選手が活躍した。",
        "relevance_score": 95,
        "relevance_decision": "accepted",
    }

    assert "published_at" not in payload


def test_analyzer_rejects_missing_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(None)

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    analyzer = OpenAIPriorityAnalyzer(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    with pytest.raises(
        OpenAIPriorityResponseError,
        match="no parsed priority output",
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
        OpenAIPriorityOutput(
            priority_score=score,
            reason="reason",
        )


def test_analyzer_rejects_empty_api_key() -> None:
    with pytest.raises(
        ValueError,
        match="API key",
    ):
        OpenAIPriorityAnalyzer(
            api_key="",
            model="gpt-5.6-luna",
            timeout_seconds=30,
        )


def test_analyzer_rejects_empty_model() -> None:
    with pytest.raises(
        ValueError,
        match="model",
    ):
        OpenAIPriorityAnalyzer(
            api_key="test-key",
            model="",
            timeout_seconds=30,
        )


@pytest.mark.parametrize(
    "timeout_seconds",
    [0, -1],
)
def test_analyzer_rejects_nonpositive_timeout(
    timeout_seconds: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="timeout_seconds",
    ):
        OpenAIPriorityAnalyzer(
            api_key="test-key",
            model="gpt-5.6-luna",
            timeout_seconds=timeout_seconds,
        )

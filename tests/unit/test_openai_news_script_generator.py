import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

import project_g.infrastructure.ai.openai_script as module
from project_g.infrastructure.ai.openai_script import (
    OpenAINewsScriptGenerator,
    OpenAINewsScriptOutput,
    OpenAINewsScriptResponseError,
)
from project_g.ports.news_script import (
    NewsScriptBackgroundFact,
    NewsScriptGeneratorInput,
)


class FakeResponses:
    def __init__(
        self,
        output: OpenAINewsScriptOutput | None,
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
        output: OpenAINewsScriptOutput | None,
    ) -> None:
        self.responses = FakeResponses(output)


def _input() -> NewsScriptGeneratorInput:
    return NewsScriptGeneratorInput(
        intake_id=UUID("00000000-0000-0000-0000-000000000001"),
        source_id="hochi_giants_articles",
        title="【巨人】新打線で8回一挙10得点",
        description=("巨人が新打線で8回に10得点を挙げた。"),
        canonical_url=("https://hochi.news/articles/example"),
        relevance_score=98,
        priority_score=96,
        ranking_score=77,
    )


def test_generator_returns_structured_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAINewsScriptOutput(
            hook="巨人打線が一気に爆発です!",
            main_narration=("巨人が新打線で8回に10得点を挙げました。"),
            project_g_comment=("この勢い、次の試合にも持っていってほしい!"),
            closing="次の巨人戦も注目です。",
            full_narration=(
                "巨人打線が一気に爆発です!"
                "巨人が新打線で8回に10得点を挙げました。"
                "この勢い、次の試合にも持っていってほしい!"
                "次の巨人戦も注目です。"
            ),
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    generator = OpenAINewsScriptGenerator(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    result = generator.generate(_input())

    assert result.hook == "巨人打線が一気に爆発です!"
    assert "8回に10得点" in result.main_narration
    assert result.project_g_comment
    assert result.closing
    assert result.full_narration

    assert fake_client.responses.kwargs is not None
    assert fake_client.responses.kwargs["model"] == "gpt-5.6-luna"
    assert fake_client.responses.kwargs["text_format"] is OpenAINewsScriptOutput
    assert fake_client.responses.kwargs["reasoning"] == {"effort": "none"}
    assert fake_client.responses.kwargs["max_output_tokens"] == 1200
    assert fake_client.responses.kwargs["store"] is False
    assert fake_client.responses.kwargs["timeout"] == 30


def test_generator_sends_only_allowed_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAINewsScriptOutput(
            hook="Hook",
            main_narration="Main",
            project_g_comment="Comment",
            closing="Closing",
            full_narration="Full",
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    generator = OpenAINewsScriptGenerator(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    generator.generate(_input())

    assert fake_client.responses.kwargs is not None

    payload = json.loads(fake_client.responses.kwargs["input"])

    assert payload == {
        "intake_id": ("00000000-0000-0000-0000-000000000001"),
        "source_id": "hochi_giants_articles",
        "title": "【巨人】新打線で8回一挙10得点",
        "description": ("巨人が新打線で8回に10得点を挙げた。"),
        "canonical_url": ("https://hochi.news/articles/example"),
        "relevance_score": 98,
        "priority_score": 96,
        "ranking_score": 77,
        "background_facts": [],
    }


def test_generator_rejects_missing_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(None)

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    generator = OpenAINewsScriptGenerator(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    with pytest.raises(
        OpenAINewsScriptResponseError,
        match="no parsed script output",
    ):
        generator.generate(_input())


@pytest.mark.parametrize(
    ("api_key", "model", "timeout_seconds"),
    [
        ("", "gpt-5.6-luna", 30),
        ("test-key", "", 30),
        ("test-key", "gpt-5.6-luna", 0),
        ("test-key", "gpt-5.6-luna", -1),
    ],
)
def test_generator_rejects_invalid_configuration(
    api_key: str,
    model: str,
    timeout_seconds: float,
) -> None:
    with pytest.raises(ValueError):
        OpenAINewsScriptGenerator(
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )


def test_generator_instructions_define_project_g_kansai_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAINewsScriptOutput(
            hook="巨人ファン注目です。",
            main_narration="巨人に関するニュースです。",
            project_g_comment="これはさすがに結果出してもらわなあかんわ。",
            closing="今後に注目です。",
            full_narration=(
                "巨人ファン注目です。"
                "巨人に関するニュースです。"
                "これはさすがに結果出してもらわなあかんわ。"
                "今後に注目です。"
            ),
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    generator = OpenAINewsScriptGenerator(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    generator.generate(_input())

    assert fake_client.responses.kwargs is not None
    instructions = fake_client.responses.kwargs["instructions"]

    assert "natural, modern spoken Kansai dialect" in instructions
    assert "Level 5 out of 5" in instructions
    assert "Do NOT sound like a comedian" in instructions
    assert "do not force negativity" in instructions
    assert "Do not overuse 「〜やで」" in instructions
    assert "「なんでやねん」 or 「知らんけど」" in instructions


def test_generator_sends_background_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAINewsScriptOutput(
            hook="Hook",
            main_narration="Main",
            project_g_comment="Comment",
            closing="Closing",
            full_narration="Full",
        )
    )

    monkeypatch.setattr(
        module,
        "OpenAI",
        lambda **kwargs: fake_client,
    )

    generator = OpenAINewsScriptGenerator(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
    )

    input_data = _input()
    input_data = NewsScriptGeneratorInput(
        intake_id=input_data.intake_id,
        source_id=input_data.source_id,
        title=input_data.title,
        description=input_data.description,
        canonical_url=input_data.canonical_url,
        relevance_score=input_data.relevance_score,
        priority_score=input_data.priority_score,
        ranking_score=input_data.ranking_score,
        background_facts=(
            NewsScriptBackgroundFact(
                text="中継ぎ起用が見込まれている。",
                source_id="verified-source",
                source_url="https://example.com/background",
            ),
        ),
    )

    generator.generate(input_data)

    assert fake_client.responses.kwargs is not None
    payload = json.loads(fake_client.responses.kwargs["input"])

    assert payload["background_facts"] == [
        {
            "text": "中継ぎ起用が見込まれている。",
            "source_id": "verified-source",
            "source_url": "https://example.com/background",
        }
    ]

    instructions = fake_client.responses.kwargs["instructions"]
    assert "main_narration must NOT use background_facts" in instructions
    assert "project_g_comment MAY use background_facts" in instructions

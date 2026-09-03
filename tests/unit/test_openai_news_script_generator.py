import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

import project_g.infrastructure.ai.openai_script as module
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
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
        "background_evidence": {
            "target": [],
            "comparison": [],
            "team_context": [],
        },
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
                competition_level=CompetitionLevel.FARM,
                role=EvidenceRole.TARGET,
            ),
        ),
    )

    generator.generate(input_data)

    assert fake_client.responses.kwargs is not None
    payload = json.loads(fake_client.responses.kwargs["input"])

    assert payload["background_evidence"] == {
        "target": [
            {
                "text": "中継ぎ起用が見込まれている。",
                "source_id": "verified-source",
                "source_url": "https://example.com/background",
                "competition_level": "farm",
            }
        ],
        "comparison": [],
        "team_context": [],
    }

    instructions = fake_client.responses.kwargs["instructions"]
    assert "main_narration must NOT use background_evidence" in instructions
    assert "project_g_comment MAY use background_evidence" in instructions
    assert 'evidence from BOTH the "target"' in instructions
    assert 'and "comparison" groups' in instructions
    assert "use concrete supported data from BOTH sides" in instructions
    assert 'If there is no "comparison" evidence' in instructions
    assert "Never present farm performance as first-team performance" in instructions
    assert "opportunity cost" in instructions
    assert "Do not describe the target or a comparison player" in instructions
    assert "experienced, established, young, in-form" in instructions
    assert "directly supports that description" in instructions
    assert "Never invent the existence" in instructions
    assert '"show results"' in instructions


def test_generator_groups_background_evidence_by_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAINewsScriptOutput(
            hook="Hook",
            main_narration="Main",
            project_g_comment="Comment",
            closing="Closing",
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

    base = _input()

    input_data = NewsScriptGeneratorInput(
        intake_id=base.intake_id,
        source_id=base.source_id,
        title=base.title,
        description=base.description,
        canonical_url=base.canonical_url,
        relevance_score=base.relevance_score,
        priority_score=base.priority_score,
        ranking_score=base.ranking_score,
        background_facts=(
            NewsScriptBackgroundFact(
                text="則本はファーム戦で6回4失点だった。",
                source_id="npb_official",
                source_url="https://example.com/target",
                competition_level=CompetitionLevel.FARM,
                role=EvidenceRole.TARGET,
            ),
            NewsScriptBackgroundFact(
                text="比較対象の投手は直近登板で無失点だった。",
                source_id="verified-source",
                source_url="https://example.com/comparison",
                competition_level=CompetitionLevel.FARM,
                role=EvidenceRole.COMPARISON,
            ),
            NewsScriptBackgroundFact(
                text="投手陣で登録変更があった。",
                source_id="verified-source",
                source_url="https://example.com/team",
                competition_level=CompetitionLevel.FIRST_TEAM,
                role=EvidenceRole.TEAM_CONTEXT,
            ),
        ),
    )

    generator.generate(input_data)

    assert fake_client.responses.kwargs is not None

    payload = json.loads(fake_client.responses.kwargs["input"])

    evidence = payload["background_evidence"]

    assert len(evidence["target"]) == 1
    assert len(evidence["comparison"]) == 1
    assert len(evidence["team_context"]) == 1

    assert evidence["target"][0]["text"] == "則本はファーム戦で6回4失点だった。"
    assert evidence["comparison"][0]["text"] == "比較対象の投手は直近登板で無失点だった。"
    assert evidence["team_context"][0]["text"] == "投手陣で登録変更があった。"


def test_generator_returns_verified_evidence_without_rewriting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAINewsScriptOutput(
            hook="Hook",
            main_narration="Main",
            project_g_comment="Comment",
            closing="Closing",
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

    base = _input()

    target_fact = NewsScriptBackgroundFact(
        text="則本はファーム戦で6回9安打4失点だった。",
        source_id="npb_official",
        source_url="https://example.com/norimoto",
        competition_level=CompetitionLevel.FARM,
        role=EvidenceRole.TARGET,
    )

    comparison_fact = NewsScriptBackgroundFact(
        text="比較対象の投手はファーム戦で6回無失点だった。",
        source_id="npb_official",
        source_url="https://example.com/comparison",
        competition_level=CompetitionLevel.FARM,
        role=EvidenceRole.COMPARISON,
    )

    input_data = NewsScriptGeneratorInput(
        intake_id=base.intake_id,
        source_id=base.source_id,
        title=base.title,
        description=base.description,
        canonical_url=base.canonical_url,
        relevance_score=base.relevance_score,
        priority_score=base.priority_score,
        ranking_score=base.ranking_score,
        background_facts=(
            target_fact,
            comparison_fact,
        ),
    )

    result = generator.generate(input_data)

    assert result.evidence_points == (
        target_fact,
        comparison_fact,
    )

    assert result.evidence_points[0].role is EvidenceRole.TARGET
    assert result.evidence_points[1].role is EvidenceRole.COMPARISON

    assert result.evidence_points[0].source_id == "npb_official"


def test_generator_builds_full_narration_with_project_g_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAINewsScriptOutput(
            hook="Hook",
            main_narration="Main fact.",
            project_g_comment="Comment.",
            closing="Closing.",
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

    assert result.full_narration == (
        "Hook\n\nMain fact.\n\nここからはPROJECT Gの見解です。\n\nComment.\n\nClosing."
    )


def test_generator_forbids_unsupported_temporal_framing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        OpenAINewsScriptOutput(
            hook="Hook",
            main_narration="Main",
            project_g_comment="Comment",
            closing="Closing",
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

    assert "unsupported temporal or emotional framing" in instructions
    assert '"finally"' in instructions
    assert "title or description directly supports it" in instructions

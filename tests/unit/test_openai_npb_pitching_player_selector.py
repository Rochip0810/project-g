from types import SimpleNamespace
from typing import Any

import pytest

import project_g.infrastructure.ai.openai_npb_player as player_module
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.infrastructure.ai.openai_npb_player import (
    OpenAINPBPitchingPlayerSelector,
)


class FakeResponses:
    def __init__(
        self,
        output_parsed: Any,
    ) -> None:
        self._output_parsed = output_parsed
        self.calls: list[dict[str, Any]] = []

    def parse(
        self,
        **kwargs: Any,
    ) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=self._output_parsed,
        )


class FakeOpenAI:
    def __init__(
        self,
        output_parsed: Any,
    ) -> None:
        self.responses = FakeResponses(output_parsed)


def _build_selector(
    monkeypatch: pytest.MonkeyPatch,
    *,
    output_parsed: Any,
) -> tuple[
    OpenAINPBPitchingPlayerSelector,
    FakeOpenAI,
]:
    fake_client = FakeOpenAI(output_parsed)

    def fake_openai(
        *,
        api_key: str,
    ) -> FakeOpenAI:
        assert api_key == "test-key"
        return fake_client

    monkeypatch.setattr(
        player_module,
        "OpenAI",
        fake_openai,
    )

    selector = OpenAINPBPitchingPlayerSelector(
        api_key="test-key",
        model="test-model",
        timeout_seconds=10,
    )

    return selector, fake_client


def test_selects_explicitly_mentioned_target_pitcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = SimpleNamespace(
        players=[
            SimpleNamespace(
                mention="則本昂大",
                lookup_name="則本",
                role=EvidenceRole.TARGET,
            ),
        ]
    )

    selector, fake_client = _build_selector(
        monkeypatch,
        output_parsed=output,
    )

    result = selector.select(
        target_title="【巨人】則本昂大が１軍合流",
        target_description=("巨人の則本昂大投手が１軍に合流した。"),
    )

    assert len(result) == 1
    assert result[0].player_name == "則本"
    assert result[0].role is EvidenceRole.TARGET

    assert len(fake_client.responses.calls) == 1
    call = fake_client.responses.calls[0]

    assert call["model"] == "test-model"
    assert call["reasoning"] == {
        "effort": "none",
    }
    assert call["store"] is False


def test_rejects_player_not_mentioned_in_article(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = SimpleNamespace(
        players=[
            SimpleNamespace(
                mention="戸郷翔征",
                lookup_name="戸郷",
                role=EvidenceRole.TARGET,
            ),
        ]
    )

    selector, _ = _build_selector(
        monkeypatch,
        output_parsed=output,
    )

    result = selector.select(
        target_title="【巨人】則本昂大が１軍合流",
        target_description=("巨人の則本昂大投手が１軍に合流した。"),
    )

    assert result == ()


def test_rejects_lookup_name_not_supported_by_mention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = SimpleNamespace(
        players=[
            SimpleNamespace(
                mention="則本昂大",
                lookup_name="戸郷",
                role=EvidenceRole.TARGET,
            ),
        ]
    )

    selector, _ = _build_selector(
        monkeypatch,
        output_parsed=output,
    )

    result = selector.select(
        target_title="【巨人】則本昂大が１軍合流",
        target_description=None,
    )

    assert result == ()

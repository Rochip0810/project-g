import pytest

from project_g.application.news.select_script_display_evidence import (
    select_script_display_evidence,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.ports.news_script import NewsScriptBackgroundFact


def _fact(
    text: str,
    role: EvidenceRole,
) -> NewsScriptBackgroundFact:
    return NewsScriptBackgroundFact(
        text=text,
        source_id="verified-source",
        source_url=f"https://example.com/{text}",
        competition_level=CompetitionLevel.FARM,
        role=role,
    )


def test_comparison_keeps_evidence_from_both_sides() -> None:
    target_1 = _fact(
        "則本8月15日",
        EvidenceRole.TARGET,
    )
    target_2 = _fact(
        "則本8月1日",
        EvidenceRole.TARGET,
    )
    comparison_1 = _fact(
        "若手A直近登板",
        EvidenceRole.COMPARISON,
    )
    comparison_2 = _fact(
        "若手B直近登板",
        EvidenceRole.COMPARISON,
    )

    result = select_script_display_evidence(
        (
            target_1,
            target_2,
            comparison_1,
            comparison_2,
        )
    )

    assert result == (
        target_1,
        comparison_1,
        target_2,
        comparison_2,
    )


def test_target_only_does_not_invent_comparison() -> None:
    target_1 = _fact(
        "則本8月15日",
        EvidenceRole.TARGET,
    )
    target_2 = _fact(
        "則本8月1日",
        EvidenceRole.TARGET,
    )

    result = select_script_display_evidence(
        (
            target_1,
            target_2,
        )
    )

    assert result == (
        target_1,
        target_2,
    )


def test_team_context_fills_remaining_space() -> None:
    target = _fact(
        "則本の成績",
        EvidenceRole.TARGET,
    )
    team_context = _fact(
        "投手陣の登録事情",
        EvidenceRole.TEAM_CONTEXT,
    )

    result = select_script_display_evidence(
        (
            target,
            team_context,
        )
    )

    assert result == (
        target,
        team_context,
    )


def test_limit_is_respected() -> None:
    facts = tuple(
        _fact(
            f"fact-{index}",
            EvidenceRole.TARGET,
        )
        for index in range(6)
    )

    result = select_script_display_evidence(
        facts,
        limit=3,
    )

    assert len(result) == 3


@pytest.mark.parametrize(
    "limit",
    (
        0,
        5,
    ),
)
def test_rejects_invalid_limit(
    limit: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="limit must be between 1 and 4",
    ):
        select_script_display_evidence(
            (),
            limit=limit,
        )

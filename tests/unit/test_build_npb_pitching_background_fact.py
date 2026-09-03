from datetime import date

from project_g.application.news.build_npb_pitching_background_fact import (
    build_npb_pitching_background_fact,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.game_evidence import (
    NPBGamePitchingEvidence,
)


def _evidence(
    *,
    competition_level: CompetitionLevel,
) -> NPBGamePitchingEvidence:
    return NPBGamePitchingEvidence(
        source_url=("https://npb.jp/scores_farm/2026/0801/g-e-09/box.html"),
        game_date=date(2026, 8, 1),
        competition_level=competition_level,
        player_name="則本",
        decision="○",
        pitches=109,
        batters_faced=27,
        innings_whole=5,
        innings_outs=2,
        hits=7,
        home_runs=1,
        walks=3,
        hit_by_pitch=0,
        strikeouts=4,
        wild_pitches=0,
        balks=0,
        runs=4,
        earned_runs=4,
    )


def test_builds_farm_background_fact() -> None:
    result = build_npb_pitching_background_fact(
        _evidence(
            competition_level=CompetitionLevel.FARM,
        )
    )

    assert result.text == (
        "2026年8月1日のファーム戦で"
        "則本は勝投手となり、"
        "5回2/3、109球、"
        "被安打7、"
        "被本塁打1、"
        "四球3、"
        "奪三振4、"
        "4失点(自責4)だった。"
    )

    assert result.source_id == "npb_official"
    assert result.source_url == ("https://npb.jp/scores_farm/2026/0801/g-e-09/box.html")
    assert result.competition_level is CompetitionLevel.FARM


def test_labels_first_team_separately() -> None:
    evidence = _evidence(
        competition_level=CompetitionLevel.FIRST_TEAM,
    )

    result = build_npb_pitching_background_fact(evidence)

    assert "1軍戦" in result.text
    assert "ファーム戦" not in result.text
    assert result.competition_level is CompetitionLevel.FIRST_TEAM


def test_can_build_comparison_background_fact() -> None:
    from project_g.domain.news.evidence_role import EvidenceRole

    result = build_npb_pitching_background_fact(
        _evidence(
            competition_level=CompetitionLevel.FARM,
        ),
        role=EvidenceRole.COMPARISON,
    )

    assert result.role is EvidenceRole.COMPARISON
    assert result.competition_level is CompetitionLevel.FARM
    assert "則本" in result.text
    assert "5回2/3" in result.text


def test_default_background_fact_role_is_target() -> None:
    from project_g.domain.news.evidence_role import EvidenceRole

    result = build_npb_pitching_background_fact(
        _evidence(
            competition_level=CompetitionLevel.FARM,
        )
    )

    assert result.role is EvidenceRole.TARGET


def test_separates_innings_and_pitch_count() -> None:
    evidence = NPBGamePitchingEvidence(
        source_url=("https://npb.jp/scores/2026/0821/g-c-15/box.html"),
        game_date=date(2026, 8, 21),
        competition_level=CompetitionLevel.FIRST_TEAM,
        player_name="堀田",
        decision="H",
        pitches=18,
        batters_faced=4,
        innings_whole=1,
        innings_outs=0,
        hits=1,
        home_runs=0,
        walks=0,
        hit_by_pitch=0,
        strikeouts=1,
        wild_pitches=0,
        balks=0,
        runs=0,
        earned_runs=0,
    )

    result = build_npb_pitching_background_fact(
        evidence,
    )

    assert "1回、18球" in result.text
    assert "118球" not in result.text

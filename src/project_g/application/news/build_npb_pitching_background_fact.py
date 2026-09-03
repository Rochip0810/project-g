from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.game_evidence import (
    NPBGamePitchingEvidence,
)
from project_g.ports.news_script import (
    NewsScriptBackgroundFact,
)

NPB_OFFICIAL_SOURCE_ID = "npb_official"


def _competition_label(
    competition_level: CompetitionLevel,
) -> str:
    if competition_level is CompetitionLevel.FARM:
        return "ファーム戦"

    if competition_level is CompetitionLevel.FIRST_TEAM:
        return "1軍戦"

    return "試合"


def _decision_phrase(
    decision: str | None,
) -> str:
    if decision == "○":
        return "勝投手となり"

    if decision == "●":
        return "敗投手となり"

    return "登板し"


def build_npb_pitching_background_fact(
    evidence: NPBGamePitchingEvidence,
    *,
    role: EvidenceRole = EvidenceRole.TARGET,
) -> NewsScriptBackgroundFact:
    game_date = f"{evidence.game_date.year}年{evidence.game_date.month}月{evidence.game_date.day}日"

    competition = _competition_label(evidence.competition_level)

    decision = _decision_phrase(evidence.decision)

    text = (
        f"{game_date}の{competition}で"
        f"{evidence.player_name}は{decision}、"
        f"{evidence.innings_display}、"
        f"{evidence.pitches}球、"
        f"被安打{evidence.hits}、"
        f"被本塁打{evidence.home_runs}、"
        f"四球{evidence.walks}、"
        f"奪三振{evidence.strikeouts}、"
        f"{evidence.runs}失点"
        f"(自責{evidence.earned_runs})だった。"
    )

    return NewsScriptBackgroundFact(
        text=text,
        source_id=NPB_OFFICIAL_SOURCE_ID,
        source_url=evidence.source_url,
        competition_level=evidence.competition_level,
        role=role,
    )

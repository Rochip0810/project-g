from dataclasses import dataclass
from datetime import date

from project_g.domain.news.competition import CompetitionLevel


@dataclass(frozen=True, slots=True)
class NPBGamePitchingEvidence:
    source_url: str
    game_date: date
    competition_level: CompetitionLevel
    player_name: str
    decision: str | None
    pitches: int
    batters_faced: int
    innings_whole: int
    innings_outs: int
    hits: int
    home_runs: int
    walks: int
    hit_by_pitch: int
    strikeouts: int
    wild_pitches: int
    balks: int
    runs: int
    earned_runs: int

    @property
    def innings_display(self) -> str:
        if self.innings_outs == 0:
            return f"{self.innings_whole}回"

        return f"{self.innings_whole}回{self.innings_outs}/3"

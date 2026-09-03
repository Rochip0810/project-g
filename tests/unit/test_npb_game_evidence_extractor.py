from datetime import date

import pytest

from project_g.domain.news.competition import CompetitionLevel
from project_g.infrastructure.background.npb_game import (
    NPBGameEvidenceExtractionError,
    NPBGameEvidenceExtractor,
)


def _html(
    *,
    whole: str = "5",
    fraction: str = ".2",
) -> str:
    return f"""
    <html>
      <body>
        <table>
          <tbody>
            <tr>
              <th></th>
              <th>投手</th>
              <th>投球数</th>
              <th>打者</th>
              <th>投球回</th>
              <th>安打</th>
              <th>本塁打</th>
              <th>四球</th>
              <th>死球</th>
              <th>三振</th>
              <th>暴投</th>
              <th>ボーク</th>
              <th>失点</th>
              <th>自責点</th>
            </tr>
            <tr>
              <td>○</td>
              <td class="player">則本</td>
              <td>109</td>
              <td>27</td>
              <td>
                <table class="table_inning">
                  <tbody>
                    <tr>
                      <th>{whole}</th>
                      <td>{fraction}</td>
                    </tr>
                  </tbody>
                </table>
              </td>
              <td>7</td>
              <td>1</td>
              <td>3</td>
              <td>0</td>
              <td>4</td>
              <td>0</td>
              <td>0</td>
              <td>4</td>
              <td>4</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """


def test_extracts_farm_pitching_line() -> None:
    result = NPBGameEvidenceExtractor().extract_pitcher(
        html=_html(),
        source_url=("https://npb.jp/scores_farm/2026/0801/g-e-09/box.html"),
        player_name="則本",
    )

    assert result.game_date == date(2026, 8, 1)
    assert result.competition_level is CompetitionLevel.FARM
    assert result.player_name == "則本"
    assert result.decision == "○"
    assert result.pitches == 109
    assert result.batters_faced == 27
    assert result.innings_whole == 5
    assert result.innings_outs == 2
    assert result.innings_display == "5回2/3"
    assert result.hits == 7
    assert result.home_runs == 1
    assert result.walks == 3
    assert result.hit_by_pitch == 0
    assert result.strikeouts == 4
    assert result.runs == 4
    assert result.earned_runs == 4


def test_extracts_complete_innings() -> None:
    result = NPBGameEvidenceExtractor().extract_pitcher(
        html=_html(
            whole="6",
            fraction="",
        ),
        source_url=("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
        player_name="則本",
    )

    assert result.innings_whole == 6
    assert result.innings_outs == 0
    assert result.innings_display == "6回"


def test_identifies_first_team_url() -> None:
    result = NPBGameEvidenceExtractor().extract_pitcher(
        html=_html(),
        source_url=("https://npb.jp/scores/2026/0825/s-g-21/box.html"),
        player_name="則本",
    )

    assert result.competition_level is CompetitionLevel.FIRST_TEAM


def test_rejects_unsupported_url() -> None:
    with pytest.raises(
        NPBGameEvidenceExtractionError,
        match="Unsupported NPB game",
    ):
        NPBGameEvidenceExtractor().extract_pitcher(
            html=_html(),
            source_url="https://npb.jp/bis/players/123.html",
            player_name="則本",
        )


def test_rejects_invalid_innings_fraction() -> None:
    with pytest.raises(
        NPBGameEvidenceExtractionError,
        match="Invalid NPB innings fraction",
    ):
        NPBGameEvidenceExtractor().extract_pitcher(
            html=_html(
                fraction=".3",
            ),
            source_url=("https://npb.jp/scores_farm/2026/0801/g-e-09/box.html"),
            player_name="則本",
        )


def test_rejects_missing_pitcher() -> None:
    with pytest.raises(
        NPBGameEvidenceExtractionError,
        match="Pitcher was not found",
    ):
        NPBGameEvidenceExtractor().extract_pitcher(
            html=_html(),
            source_url=("https://npb.jp/scores_farm/2026/0801/g-e-09/box.html"),
            player_name="菅野",
        )

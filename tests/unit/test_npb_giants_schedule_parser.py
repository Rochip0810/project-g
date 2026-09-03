from datetime import UTC, datetime

from project_g.infrastructure.background.npb_schedule import (
    NPBGiantsScheduleParser,
)


def test_extracts_first_team_giants_box_urls() -> None:
    html = """
    <html>
      <body>
        <table>
          <tr>
            <td>
              巨人
              <a href="/scores/2026/0821/g-c-15/">4 - 2</a>
              広島
            </td>
          </tr>
          <tr>
            <td>
              阪神
              <a href="/scores/2026/0821/t-db-18/">3 - 1</a>
              DeNA
            </td>
          </tr>
          <tr>
            <td>
              巨人
              <a href="/scores/2026/0822/g-c-16/">5 - 3</a>
              広島
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    result = NPBGiantsScheduleParser().parse(
        html=html,
        source_url=("https://npb.jp/games/2026/schedule_08_detail.html"),
    )

    assert result == (
        "https://npb.jp/scores/2026/0821/g-c-15/box.html",
        "https://npb.jp/scores/2026/0822/g-c-16/box.html",
    )


def test_extracts_farm_giants_box_urls() -> None:
    html = """
    <html>
      <body>
        <table>
          <tr>
            <td>
              巨人
              <a href="/scores_farm/2026/0801/g-e-09/">9 - 6</a>
              楽天
            </td>
          </tr>
          <tr>
            <td>
              巨人
              <a href="/scores_farm/2026/0815/g-a-04/">6 - 4</a>
              日本ハム
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    result = NPBGiantsScheduleParser().parse(
        html=html,
        source_url=("https://npb.jp/farm/2026/schedule_08_detail.html"),
    )

    assert result == (
        "https://npb.jp/scores_farm/2026/0801/g-e-09/box.html",
        "https://npb.jp/scores_farm/2026/0815/g-a-04/box.html",
    )


def test_ignores_non_npb_and_wrong_score_paths() -> None:
    html = """
    <html>
      <body>
        <table>
          <tr>
            <td>
              巨人
              <a href="https://example.com/scores/2026/0822/x/">5 - 3</a>
              広島
            </td>
          </tr>
          <tr>
            <td>
              巨人
              <a href="/players/123456/">選手</a>
              広島
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    result = NPBGiantsScheduleParser().parse(
        html=html,
        source_url=("https://npb.jp/games/2026/schedule_08_detail.html"),
    )

    assert result == ()


def test_deduplicates_urls_preserving_order() -> None:
    html = """
    <html>
      <body>
        <table>
          <tr>
            <td>
              巨人
              <a href="/scores/2026/0822/g-c-16/">5 - 3</a>
              広島
              <a href="/scores/2026/0822/g-c-16/">詳細</a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    result = NPBGiantsScheduleParser().parse(
        html=html,
        source_url=("https://npb.jp/games/2026/schedule_08_detail.html"),
    )

    assert result == ("https://npb.jp/scores/2026/0822/g-c-16/box.html",)


def test_filters_game_urls_by_jst_date_window() -> None:
    html = """
    <html>
      <body>
        <a href="/scores/2026/0807/g-c-13/">old</a>
        <a href="/scores/2026/0808/g-c-14/">boundary</a>
        <a href="/scores/2026/0822/g-c-16/">same day</a>
        <a href="/scores/2026/0823/g-c-17/">future</a>
      </body>
    </html>
    """

    published_until = datetime(
        2026,
        8,
        22,
        0,
        47,
        tzinfo=UTC,
    )

    result = NPBGiantsScheduleParser().parse(
        html=html,
        source_url=("https://npb.jp/games/2026/schedule_08_detail.html"),
        published_until=published_until,
        lookback_days=14,
    )

    assert result == (
        "https://npb.jp/scores/2026/0808/g-c-14/box.html",
        "https://npb.jp/scores/2026/0822/g-c-16/box.html",
    )

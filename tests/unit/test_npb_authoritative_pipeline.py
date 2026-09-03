from datetime import UTC, datetime
from uuid import UUID

from project_g.application.news.collect_npb_authoritative_facts import (
    CollectNPBAuthoritativeFacts,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.infrastructure.background.npb_discovery import (
    NPBOfficialPitchingEvidenceDiscovery,
)
from project_g.infrastructure.background.npb_game import (
    NPBGameEvidenceExtractor,
)
from project_g.infrastructure.background.npb_schedule import (
    NPBGiantsGameUrlDiscovery,
    NPBGiantsScheduleParser,
)
from project_g.ports.http import HttpResponse
from project_g.ports.npb_game import (
    NPBPitchingPlayerCandidate,
)

_TARGET_ID = UUID("2c4c3406-7e28-4207-966e-2cd5dfb5e5e5")

_TITLE = "【巨人】則本昂大が１軍合流 東京ドームに姿見せる - スポーツ報知"

_DESCRIPTION = (
    "巨人の則本昂大投手が２２日、１軍に合流した。"
    "東京ドームで行われる広島戦の試合前練習から"
    "姿を見せた。"
)

_PUBLISHED_UNTIL = datetime(
    2026,
    8,
    22,
    0,
    47,
    tzinfo=UTC,
)

_FIRST_TEAM_SCHEDULE = "https://npb.jp/games/2026/schedule_08_detail.html"

_FARM_SCHEDULE = "https://npb.jp/farm/2026/schedule_08_detail.html"

_AUGUST_1_BOX = "https://npb.jp/scores_farm/2026/0801/g-e-09/box.html"

_AUGUST_15_BOX = "https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"


class FakePlayerSelector:
    def select(
        self,
        *,
        target_title: str,
        target_description: str | None,
    ) -> tuple[NPBPitchingPlayerCandidate, ...]:
        assert "則本昂大" in target_title
        assert target_description is not None
        assert "則本昂大" in target_description

        return (
            NPBPitchingPlayerCandidate(
                player_name="則本",
                role=EvidenceRole.TARGET,
            ),
        )


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

        self._pages = {
            _FIRST_TEAM_SCHEDULE: """
                <html>
                  <body>
                    <p>対象期間に則本の一軍登板なし</p>
                  </body>
                </html>
            """,
            _FARM_SCHEDULE: """
                <html>
                  <body>
                    <a href="/scores_farm/2026/0801/g-e-09/">
                      8月1日 巨人戦
                    </a>
                    <a href="/scores_farm/2026/0815/g-a-04/">
                      8月15日 巨人戦
                    </a>
                  </body>
                </html>
            """,
            _AUGUST_15_BOX: """
                <html>
                  <body>
                    <div>
                      【試合終了】
                      ◇開始 18:01
                      ◇終了 20:51
                      ◇試合時間 2時間50分
                    </div>

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
                          <td>84</td>
                          <td>27</td>
                          <td>
                            <table class="table_inning">
                              <tbody>
                                <tr>
                                  <th>6</th>
                                  <td></td>
                                </tr>
                              </tbody>
                            </table>
                          </td>
                          <td>9</td>
                          <td>1</td>
                          <td>0</td>
                          <td>0</td>
                          <td>3</td>
                          <td>0</td>
                          <td>0</td>
                          <td>4</td>
                          <td>3</td>
                        </tr>
                      </tbody>
                    </table>
                  </body>
                </html>
            """,
        }

    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
        assert timeout_seconds == 10
        assert max_response_bytes == 512_000
        assert allowed_hosts == frozenset({"npb.jp"})

        self.calls.append(url)

        return HttpResponse(
            requested_url=url,
            final_url=url,
            status_code=200,
            headers={
                "content-type": "text/html; charset=utf-8",
            },
            body=self._pages[url].encode(),
        )


def test_norimoto_article_reaches_verified_npb_background_fact() -> None:
    http_client = FakeHttpClient()

    game_url_discovery = NPBGiantsGameUrlDiscovery(
        http_client=http_client,
        parser=NPBGiantsScheduleParser(),
        timeout_seconds=10,
        max_response_bytes=512_000,
    )

    evidence_discovery = NPBOfficialPitchingEvidenceDiscovery(
        player_selector=FakePlayerSelector(),
        game_url_discovery=game_url_discovery,
        lookback_days=14,
    )

    provider = CollectNPBAuthoritativeFacts(
        discovery=evidence_discovery,
        http_client=http_client,
        extractor=NPBGameEvidenceExtractor(),
        timeout_seconds=10,
        max_response_bytes=512_000,
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title=_TITLE,
        target_description=_DESCRIPTION,
        target_canonical_url=("https://hochi.news/articles/20260822-OHT1T51073.html"),
        published_until=_PUBLISHED_UNTIL,
    )

    assert http_client.calls == [
        _FIRST_TEAM_SCHEDULE,
        _FARM_SCHEDULE,
        _AUGUST_15_BOX,
    ]

    assert _AUGUST_1_BOX not in http_client.calls

    assert len(facts) == 1

    fact = facts[0]

    assert fact.source_id == "npb_official"
    assert fact.source_url == _AUGUST_15_BOX
    assert fact.competition_level is CompetitionLevel.FARM
    assert fact.role is EvidenceRole.TARGET

    assert "則本" in fact.text
    assert "6回" in fact.text
    assert "84球" in fact.text
    assert "被安打9" in fact.text

from datetime import UTC, datetime

from project_g.infrastructure.background.npb_schedule import (
    NPBGiantsGameUrlDiscovery,
    NPBGiantsScheduleParser,
)
from project_g.ports.http import HttpResponse


class FakeHttpClient:
    def __init__(
        self,
        pages: dict[str, str],
    ) -> None:
        self._pages = pages
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
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


def test_discovers_first_team_and_farm_across_month_boundary() -> None:
    july_first = "https://npb.jp/games/2026/schedule_07_detail.html"
    july_farm = "https://npb.jp/farm/2026/schedule_07_detail.html"
    august_first = "https://npb.jp/games/2026/schedule_08_detail.html"
    august_farm = "https://npb.jp/farm/2026/schedule_08_detail.html"

    pages = {
        july_first: """
            <a href="/scores/2026/0725/g-c-12/">
              巨人戦
            </a>
        """,
        july_farm: """
            <a href="/scores_farm/2026/0728/g-e-08/">
              巨人戦
            </a>
        """,
        august_first: """
            <a href="/scores/2026/0801/g-db-15/">
              巨人戦
            </a>
        """,
        august_farm: """
            <a href="/scores_farm/2026/0802/g-e-10/">
              巨人戦
            </a>
        """,
    }

    http_client = FakeHttpClient(pages)

    discovery = NPBGiantsGameUrlDiscovery(
        http_client=http_client,
        parser=NPBGiantsScheduleParser(),
        timeout_seconds=10,
        max_response_bytes=512_000,
    )

    result = discovery.discover(
        published_until=datetime(
            2026,
            8,
            3,
            0,
            47,
            tzinfo=UTC,
        ),
        lookback_days=14,
    )

    assert http_client.calls == [
        july_first,
        july_farm,
        august_first,
        august_farm,
    ]

    assert result == (
        "https://npb.jp/scores/2026/0725/g-c-12/box.html",
        "https://npb.jp/scores_farm/2026/0728/g-e-08/box.html",
        "https://npb.jp/scores/2026/0801/g-db-15/box.html",
        "https://npb.jp/scores_farm/2026/0802/g-e-10/box.html",
    )

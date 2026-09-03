from datetime import UTC, datetime
from uuid import UUID

from project_g.domain.news.evidence_role import EvidenceRole
from project_g.infrastructure.background.npb_discovery import (
    NPBOfficialPitchingEvidenceDiscovery,
)
from project_g.ports.npb_game import (
    NPBPitchingPlayerCandidate,
)

_TARGET_ID = UUID("2c4c3406-7e28-4207-966e-2cd5dfb5e5e5")


class FakePlayerSelector:
    def select(
        self,
        *,
        target_title: str,
        target_description: str | None,
    ) -> tuple[NPBPitchingPlayerCandidate, ...]:
        return (
            NPBPitchingPlayerCandidate(
                player_name="則本",
                role=EvidenceRole.TARGET,
            ),
        )


class FakeGameUrlDiscovery:
    def __init__(
        self,
        urls: tuple[str, ...],
    ) -> None:
        self._urls = urls
        self.calls: list[tuple[datetime, int]] = []

    def discover(
        self,
        *,
        published_until: datetime,
        lookback_days: int = 14,
    ) -> tuple[str, ...]:
        self.calls.append(
            (
                published_until,
                lookback_days,
            )
        )
        return self._urls


def test_builds_target_requests_for_verified_game_urls() -> None:
    urls = (
        ("https://npb.jp/scores_farm/2026/0801/g-e-09/box.html"),
        ("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
    )

    game_url_discovery = FakeGameUrlDiscovery(urls)

    discovery = NPBOfficialPitchingEvidenceDiscovery(
        player_selector=FakePlayerSelector(),
        game_url_discovery=game_url_discovery,
        lookback_days=14,
    )

    published_until = datetime(
        2026,
        8,
        22,
        0,
        47,
        tzinfo=UTC,
    )

    result = discovery.discover(
        target_intake_id=_TARGET_ID,
        target_title="【巨人】則本昂大が１軍合流",
        target_description=("巨人の則本昂大投手が１軍に合流した。"),
        target_canonical_url=("https://example.com/norimoto"),
        published_until=published_until,
    )

    assert game_url_discovery.calls == [
        (
            published_until,
            14,
        )
    ]

    assert len(result) == 2

    assert result[0].source_url == urls[0]
    assert result[0].player_name == "則本"
    assert result[0].role is EvidenceRole.TARGET

    assert result[1].source_url == urls[1]
    assert result[1].player_name == "則本"
    assert result[1].role is EvidenceRole.TARGET


def test_skips_schedule_discovery_when_no_player_is_selected() -> None:
    class EmptyPlayerSelector:
        def select(
            self,
            *,
            target_title: str,
            target_description: str | None,
        ) -> tuple[NPBPitchingPlayerCandidate, ...]:
            return ()

    game_url_discovery = FakeGameUrlDiscovery(("https://npb.jp/scores/2026/0821/g-c-15/box.html",))

    discovery = NPBOfficialPitchingEvidenceDiscovery(
        player_selector=EmptyPlayerSelector(),
        game_url_discovery=game_url_discovery,
        lookback_days=14,
    )

    result = discovery.discover(
        target_intake_id=_TARGET_ID,
        target_title="巨人が勝利",
        target_description=None,
        target_canonical_url=("https://example.com/article"),
        published_until=datetime(
            2026,
            8,
            22,
            0,
            47,
            tzinfo=UTC,
        ),
    )

    assert result == ()
    assert game_url_discovery.calls == []

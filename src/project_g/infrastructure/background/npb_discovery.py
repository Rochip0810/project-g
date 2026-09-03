from datetime import datetime
from uuid import UUID

from project_g.ports.npb_game import (
    NPBGameUrlDiscovery,
    NPBPitchingEvidenceRequest,
    NPBPitchingPlayerSelector,
)


class NPBOfficialPitchingEvidenceDiscovery:
    def __init__(
        self,
        *,
        player_selector: NPBPitchingPlayerSelector,
        game_url_discovery: NPBGameUrlDiscovery,
        lookback_days: int = 14,
    ) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be greater than zero")

        self._player_selector = player_selector
        self._game_url_discovery = game_url_discovery
        self._lookback_days = lookback_days

    def discover(
        self,
        *,
        target_intake_id: UUID,
        target_title: str,
        target_description: str | None,
        target_canonical_url: str,
        published_until: datetime,
    ) -> tuple[NPBPitchingEvidenceRequest, ...]:
        if published_until.tzinfo is None or published_until.utcoffset() is None:
            raise ValueError("published_until must be timezone-aware")

        candidates = self._player_selector.select(
            target_title=target_title,
            target_description=target_description,
        )

        if not candidates:
            return ()

        game_urls = self._game_url_discovery.discover(
            published_until=published_until,
            lookback_days=self._lookback_days,
        )

        requests: list[NPBPitchingEvidenceRequest] = []
        seen: set[NPBPitchingEvidenceRequest] = set()

        for candidate in candidates:
            for game_url in game_urls:
                request = NPBPitchingEvidenceRequest(
                    source_url=game_url,
                    player_name=candidate.player_name,
                    role=candidate.role,
                )

                if request in seen:
                    continue

                seen.add(request)
                requests.append(request)

        return tuple(requests)

from datetime import datetime
from uuid import UUID

from project_g.application.news.build_npb_pitching_background_fact import (
    build_npb_pitching_background_fact,
)
from project_g.ports.http import HttpClient, HttpClientError
from project_g.ports.news_script import NewsScriptBackgroundFact
from project_g.ports.npb_game import (
    NPBGameEvidenceExtractionError,
    NPBPitchingEvidenceDiscovery,
    NPBPitchingEvidenceExtractor,
)

_NPB_ALLOWED_HOSTS = frozenset({"npb.jp"})


class CollectNPBAuthoritativeFacts:
    def __init__(
        self,
        *,
        discovery: NPBPitchingEvidenceDiscovery,
        http_client: HttpClient,
        extractor: NPBPitchingEvidenceExtractor,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")

        self._discovery = discovery
        self._http_client = http_client
        self._extractor = extractor
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    def collect(
        self,
        *,
        target_intake_id: UUID,
        target_title: str,
        target_description: str | None,
        target_canonical_url: str,
        published_until: datetime,
    ) -> tuple[NewsScriptBackgroundFact, ...]:
        if published_until.tzinfo is None or published_until.utcoffset() is None:
            raise ValueError("published_until must be timezone-aware")

        requests = self._discovery.discover(
            target_intake_id=target_intake_id,
            target_title=target_title,
            target_description=target_description,
            target_canonical_url=target_canonical_url,
            published_until=published_until,
        )

        facts: list[NewsScriptBackgroundFact] = []

        for request in requests:
            try:
                response = self._http_client.get(
                    request.source_url,
                    timeout_seconds=self._timeout_seconds,
                    max_response_bytes=self._max_response_bytes,
                    allowed_hosts=_NPB_ALLOWED_HOSTS,
                )

                evidence = self._extractor.extract_pitcher(
                    html=response.text,
                    source_url=response.final_url,
                    player_name=request.player_name,
                )
            except (
                HttpClientError,
                NPBGameEvidenceExtractionError,
            ):
                continue

            game_ended_at = evidence.game_ended_at

            if game_ended_at is None:
                continue

            if game_ended_at.tzinfo is None or game_ended_at.utcoffset() is None:
                continue

            if game_ended_at > published_until:
                continue

            facts.append(
                build_npb_pitching_background_fact(
                    evidence,
                    role=request.role,
                )
            )

        return tuple(facts)

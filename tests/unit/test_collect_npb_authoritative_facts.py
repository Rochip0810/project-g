from datetime import UTC, date, datetime
from uuid import UUID

from project_g.application.news.collect_npb_authoritative_facts import (
    CollectNPBAuthoritativeFacts,
)
from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.game_evidence import (
    NPBGamePitchingEvidence,
)
from project_g.ports.http import HttpResponse, HttpTimeoutError
from project_g.ports.npb_game import (
    NPBGameEvidenceExtractionError,
    NPBPitchingEvidenceRequest,
)

_TARGET_ID = UUID("2c4c3406-7e28-4207-966e-2cd5dfb5e5e5")

_BEFORE_RESULT = datetime(
    2026,
    8,
    22,
    0,
    0,
    tzinfo=UTC,
)

_RESULT_AVAILABLE_AT = datetime(
    2026,
    8,
    22,
    4,
    0,
    tzinfo=UTC,
)

_AFTER_RESULT = datetime(
    2026,
    8,
    22,
    5,
    0,
    tzinfo=UTC,
)


def _evidence(
    *,
    source_url: str,
    player_name: str = "則本",
    game_ended_at: datetime | None = _RESULT_AVAILABLE_AT,
) -> NPBGamePitchingEvidence:
    return NPBGamePitchingEvidence(
        source_url=source_url,
        game_date=date(2026, 8, 22),
        competition_level=CompetitionLevel.FIRST_TEAM,
        player_name=player_name,
        decision="●",
        pitches=30,
        batters_faced=8,
        innings_whole=1,
        innings_outs=0,
        hits=4,
        home_runs=1,
        walks=1,
        hit_by_pitch=0,
        strikeouts=1,
        wild_pitches=0,
        balks=0,
        runs=3,
        earned_runs=3,
        game_ended_at=game_ended_at,
    )


class FakeDiscovery:
    def __init__(
        self,
        requests: tuple[NPBPitchingEvidenceRequest, ...],
    ) -> None:
        self._requests = requests

    def discover(
        self,
        *,
        target_intake_id: UUID,
        target_title: str,
        target_description: str | None,
        target_canonical_url: str,
        published_until: datetime,
    ) -> tuple[NPBPitchingEvidenceRequest, ...]:
        return self._requests


class FakeHttpClient:
    def __init__(self) -> None:
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
            body=b"<html></html>",
        )


class FakeExtractor:
    def __init__(
        self,
        evidence: NPBGamePitchingEvidence,
    ) -> None:
        self._evidence = evidence

    def extract_pitcher(
        self,
        *,
        html: str,
        source_url: str,
        player_name: str,
    ) -> NPBGamePitchingEvidence:
        return self._evidence


def _provider(
    *,
    request: NPBPitchingEvidenceRequest,
    evidence: NPBGamePitchingEvidence,
) -> tuple[
    CollectNPBAuthoritativeFacts,
    FakeHttpClient,
]:
    http_client = FakeHttpClient()

    provider = CollectNPBAuthoritativeFacts(
        discovery=FakeDiscovery((request,)),
        http_client=http_client,
        extractor=FakeExtractor(evidence),
        timeout_seconds=10,
        max_response_bytes=512_000,
    )

    return provider, http_client


def test_collect_uses_same_day_evidence_when_available_before_target() -> None:
    source_url = "https://npb.jp/scores/2026/0822/g-c-16/box.html"

    request = NPBPitchingEvidenceRequest(
        source_url=source_url,
        player_name="則本",
        role=EvidenceRole.TARGET,
    )

    provider, http_client = _provider(
        request=request,
        evidence=_evidence(
            source_url=source_url,
        ),
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title="則本が登板後にコメント",
        target_description=None,
        target_canonical_url="https://example.com/after",
        published_until=_AFTER_RESULT,
    )

    assert len(http_client.calls) == 1
    assert len(facts) == 1
    assert facts[0].source_id == "npb_official"
    assert facts[0].role is EvidenceRole.TARGET
    assert "則本" in facts[0].text
    assert "3失点" in facts[0].text


def test_collect_excludes_evidence_when_official_end_is_after_target() -> None:
    source_url = "https://npb.jp/scores/2026/0822/g-c-16/box.html"

    request = NPBPitchingEvidenceRequest(
        source_url=source_url,
        player_name="則本",
        role=EvidenceRole.TARGET,
    )

    provider, http_client = _provider(
        request=request,
        evidence=_evidence(
            source_url=source_url,
        ),
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title="則本が1軍合流",
        target_description=None,
        target_canonical_url="https://example.com/before",
        published_until=_BEFORE_RESULT,
    )

    assert facts == ()
    assert len(http_client.calls) == 1


class FailingHttpClient:
    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
        raise HttpTimeoutError("NPB request timed out")


class FailingExtractor:
    def extract_pitcher(
        self,
        *,
        html: str,
        source_url: str,
        player_name: str,
    ) -> NPBGamePitchingEvidence:
        raise NPBGameEvidenceExtractionError("Invalid NPB pitching page")


def test_collect_skips_http_failure() -> None:
    source_url = "https://npb.jp/scores/2026/0822/g-c-16/box.html"

    request = NPBPitchingEvidenceRequest(
        source_url=source_url,
        player_name="則本",
        role=EvidenceRole.TARGET,
    )

    provider = CollectNPBAuthoritativeFacts(
        discovery=FakeDiscovery((request,)),
        http_client=FailingHttpClient(),
        extractor=FakeExtractor(
            _evidence(
                source_url=source_url,
            )
        ),
        timeout_seconds=10,
        max_response_bytes=512_000,
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title="則本が登板後にコメント",
        target_description=None,
        target_canonical_url="https://example.com/after",
        published_until=_AFTER_RESULT,
    )

    assert facts == ()


def test_collect_skips_extraction_failure() -> None:
    source_url = "https://npb.jp/scores/2026/0822/g-c-16/box.html"

    request = NPBPitchingEvidenceRequest(
        source_url=source_url,
        player_name="則本",
        role=EvidenceRole.TARGET,
    )

    provider = CollectNPBAuthoritativeFacts(
        discovery=FakeDiscovery((request,)),
        http_client=FakeHttpClient(),
        extractor=FailingExtractor(),
        timeout_seconds=10,
        max_response_bytes=512_000,
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title="則本が登板後にコメント",
        target_description=None,
        target_canonical_url="https://example.com/after",
        published_until=_AFTER_RESULT,
    )

    assert facts == ()


class FailFirstHttpClient:
    def __init__(self) -> None:
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

        if len(self.calls) == 1:
            raise HttpTimeoutError("first NPB request timed out")

        return HttpResponse(
            requested_url=url,
            final_url=url,
            status_code=200,
            headers={
                "content-type": "text/html; charset=utf-8",
            },
            body=b"<html></html>",
        )


def test_collect_continues_after_one_evidence_failure() -> None:
    failed_url = "https://npb.jp/scores/2026/0821/g-c-14/box.html"
    successful_url = "https://npb.jp/scores/2026/0821/g-c-15/box.html"

    failed_request = NPBPitchingEvidenceRequest(
        source_url=failed_url,
        player_name="赤星",
        role=EvidenceRole.COMPARISON,
    )
    successful_request = NPBPitchingEvidenceRequest(
        source_url=successful_url,
        player_name="堀田",
        role=EvidenceRole.COMPARISON,
    )

    http_client = FailFirstHttpClient()

    provider = CollectNPBAuthoritativeFacts(
        discovery=FakeDiscovery(
            (
                failed_request,
                successful_request,
            )
        ),
        http_client=http_client,
        extractor=FakeExtractor(
            _evidence(
                source_url=successful_url,
                player_name="堀田",
            )
        ),
        timeout_seconds=10,
        max_response_bytes=512_000,
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title="則本についてのニュース",
        target_description=None,
        target_canonical_url="https://example.com/article",
        published_until=_AFTER_RESULT,
    )

    assert http_client.calls == [
        failed_url,
        successful_url,
    ]
    assert len(facts) == 1
    assert facts[0].source_url == successful_url
    assert facts[0].role is EvidenceRole.COMPARISON
    assert "堀田" in facts[0].text


def test_collect_rejects_official_game_end_after_target_time() -> None:
    source_url = "https://npb.jp/scores/2026/0822/g-c-16/box.html"

    official_future_end = datetime(
        2026,
        8,
        22,
        6,
        0,
        tzinfo=UTC,
    )

    request = NPBPitchingEvidenceRequest(
        source_url=source_url,
        player_name="則本",
        role=EvidenceRole.TARGET,
    )

    provider, http_client = _provider(
        request=request,
        evidence=_evidence(
            source_url=source_url,
            game_ended_at=official_future_end,
        ),
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title="則本についての記事",
        target_description=None,
        target_canonical_url="https://example.com/article",
        published_until=_AFTER_RESULT,
    )

    assert len(http_client.calls) == 1
    assert facts == ()


def test_collect_rejects_evidence_without_official_game_end_time() -> None:
    source_url = "https://npb.jp/scores/2026/0822/g-c-16/box.html"

    request = NPBPitchingEvidenceRequest(
        source_url=source_url,
        player_name="則本",
        role=EvidenceRole.TARGET,
    )

    provider, http_client = _provider(
        request=request,
        evidence=_evidence(
            source_url=source_url,
            game_ended_at=None,
        ),
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title="則本についての記事",
        target_description=None,
        target_canonical_url="https://example.com/article",
        published_until=_AFTER_RESULT,
    )

    assert len(http_client.calls) == 1
    assert facts == ()


def test_collect_uses_verified_official_end_time() -> None:
    source_url = "https://npb.jp/scores/2026/0822/g-c-16/box.html"

    request = NPBPitchingEvidenceRequest(
        source_url=source_url,
        player_name="則本",
        role=EvidenceRole.TARGET,
    )

    provider, http_client = _provider(
        request=request,
        evidence=_evidence(
            source_url=source_url,
            game_ended_at=_RESULT_AVAILABLE_AT,
        ),
    )

    facts = provider.collect(
        target_intake_id=_TARGET_ID,
        target_title="則本についての記事",
        target_description=None,
        target_canonical_url="https://example.com/article",
        published_until=_AFTER_RESULT,
    )

    assert len(http_client.calls) == 1
    assert len(facts) == 1
    assert facts[0].source_url == source_url

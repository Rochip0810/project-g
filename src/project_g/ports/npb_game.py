from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.game_evidence import (
    NPBGamePitchingEvidence,
)


class NPBGameEvidenceExtractionError(ValueError):
    pass


class NPBPitchingEvidenceExtractor(Protocol):
    def extract_pitcher(
        self,
        *,
        html: str,
        source_url: str,
        player_name: str,
    ) -> NPBGamePitchingEvidence:
        """Extract verified pitching evidence from an NPB page."""
        ...


@dataclass(frozen=True, slots=True)
class NPBPitchingEvidenceRequest:
    source_url: str
    player_name: str
    role: EvidenceRole


@dataclass(frozen=True, slots=True)
class NPBPitchingPlayerCandidate:
    player_name: str
    role: EvidenceRole


class NPBPitchingPlayerSelector(Protocol):
    def select(
        self,
        *,
        target_title: str,
        target_description: str | None,
    ) -> tuple[NPBPitchingPlayerCandidate, ...]:
        """Select players whose official NPB pitching evidence should be checked."""
        ...


class NPBGameUrlDiscovery(Protocol):
    def discover(
        self,
        *,
        published_until: datetime,
        lookback_days: int = 14,
    ) -> tuple[str, ...]:
        """Discover official NPB Giants game URLs."""
        ...


class NPBPitchingEvidenceDiscovery(Protocol):
    def discover(
        self,
        *,
        target_intake_id: UUID,
        target_title: str,
        target_description: str | None,
        target_canonical_url: str,
        published_until: datetime,
    ) -> tuple[NPBPitchingEvidenceRequest, ...]:
        """Discover NPB evidence candidates to verify."""
        ...

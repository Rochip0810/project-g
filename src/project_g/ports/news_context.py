from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.evidence_role import EvidenceRole
from project_g.domain.news.recent_context import RecentNewsContextItem


@dataclass(frozen=True, slots=True)
class NewsContextSelectorInput:
    target_title: str
    target_description: str | None
    candidates: tuple[RecentNewsContextItem, ...]


@dataclass(frozen=True, slots=True)
class NewsContextSelectedFact:
    text: str
    source_intake_id: UUID
    source_id: str
    source_url: str
    competition_level: CompetitionLevel = CompetitionLevel.UNKNOWN
    role: EvidenceRole = EvidenceRole.TARGET


@dataclass(frozen=True, slots=True)
class NewsContextSelectorResult:
    facts: tuple[NewsContextSelectedFact, ...]


class NewsContextSelector(Protocol):
    def select(
        self,
        input_data: NewsContextSelectorInput,
    ) -> NewsContextSelectorResult:
        """Select verified background facts relevant to one target news item."""
        ...

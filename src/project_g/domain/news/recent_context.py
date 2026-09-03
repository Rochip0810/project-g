from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from project_g.domain.news.competition import CompetitionLevel


@dataclass(frozen=True, slots=True)
class RecentNewsContextItem:
    intake_id: UUID
    source_id: str
    canonical_url: str
    title: str
    description: str | None
    published_at: datetime
    competition_level: CompetitionLevel = CompetitionLevel.UNKNOWN

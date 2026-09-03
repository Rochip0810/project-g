from datetime import datetime
from typing import Protocol
from uuid import UUID

from project_g.domain.news.recent_context import RecentNewsContextItem


class RecentNewsContextRepository(Protocol):
    def list_recent_context(
        self,
        *,
        exclude_intake_id: UUID,
        published_since: datetime,
        published_until: datetime,
        limit: int = 50,
    ) -> list[RecentNewsContextItem]:
        """Return recent usable news context excluding the target article."""
        ...

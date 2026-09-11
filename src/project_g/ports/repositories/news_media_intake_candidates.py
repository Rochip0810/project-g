from typing import Protocol

from project_g.domain.news.script_generation import (
    NewsScriptGeneration,
)


class NewsMediaIntakeCandidateRepository(Protocol):
    def list_candidates(
        self,
        *,
        media_version: int,
        limit: int,
    ) -> tuple[NewsScriptGeneration, ...]:
        """Return generated scripts needing media-production intake."""
        ...

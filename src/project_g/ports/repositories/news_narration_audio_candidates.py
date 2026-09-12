from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from project_g.domain.news.media_production import (
    NewsMediaProduction,
)


@dataclass(frozen=True, slots=True)
class NewsNarrationAudioCandidate:
    media_production: NewsMediaProduction
    full_narration: str


class NewsNarrationAudioCandidateRepository(Protocol):
    def list_candidates(
        self,
        *,
        audio_version: int,
        stale_before: datetime,
        limit: int,
    ) -> tuple[NewsNarrationAudioCandidate, ...]:
        """Return media productions eligible for narration audio."""
        ...

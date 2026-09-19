from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from project_g.domain.news.media_production import (
    NewsMediaProduction,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
)


@dataclass(frozen=True, slots=True)
class NewsVideoCandidate:
    media_production: NewsMediaProduction
    source_audio: NewsNarrationAudioGeneration


class NewsVideoCandidateRepository(Protocol):
    def list_candidates(
        self,
        *,
        audio_version: int,
        video_version: int,
        stale_before: datetime,
        limit: int,
    ) -> tuple[NewsVideoCandidate, ...]:
        """Return media productions eligible for video generation."""
        ...

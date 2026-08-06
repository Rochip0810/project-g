from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class NewsMetadataExtractionError(RuntimeError):
    """Raised when safe metadata extraction cannot finish."""


@dataclass(frozen=True, slots=True)
class ExtractedNewsMetadata:
    title: str
    published_at: datetime | None
    description: str | None


class NewsMetadataParser(Protocol):
    def parse(
        self,
        html: str,
    ) -> ExtractedNewsMetadata: ...

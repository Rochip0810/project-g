import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse


class SourceType(StrEnum):
    WEBSITE = "website"
    RSS = "rss"
    API = "api"


class SourceStatus(StrEnum):
    ENABLED = "enabled"
    PAUSED = "paused"
    DISABLED = "disabled"


def validate_http_url(url: str, *, field_name: str) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute HTTP or HTTPS URL")


@dataclass(frozen=True, slots=True)
class NewsSource:
    source_id: str
    name: str
    source_type: SourceType
    base_url: str
    is_official: bool
    status: SourceStatus = SourceStatus.ENABLED
    priority: int = 50

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", self.source_id):
            raise ValueError(
                "source_id must contain 2-64 lowercase letters, numbers, underscores, or hyphens"
            )

        if not self.name.strip():
            raise ValueError("Source name must not be empty")

        validate_http_url(
            self.base_url,
            field_name="base_url",
        )

        if not 1 <= self.priority <= 100:
            raise ValueError("Source priority must be between 1 and 100")

    @property
    def collectable(self) -> bool:
        return self.status is SourceStatus.ENABLED

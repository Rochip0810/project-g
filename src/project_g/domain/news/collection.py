from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from project_g.domain.news.source import (
    NewsSource,
    validate_http_url,
)


class CollectionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    EMPTY = "empty"
    FAILED = "failed"


def validate_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")


@dataclass(frozen=True, slots=True)
class CollectionRequest:
    source: NewsSource
    timeout_seconds: float
    max_items: int = 50
    collected_after: datetime | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if not 1 <= self.max_items <= 500:
            raise ValueError("max_items must be between 1 and 500")

        if self.collected_after is not None:
            validate_aware_datetime(
                self.collected_after,
                field_name="collected_after",
            )


@dataclass(frozen=True, slots=True)
class CollectedNewsItem:
    source_id: str
    source_name: str
    title: str
    source_url: str
    canonical_url: str
    collected_at: datetime
    published_at: datetime | None = None
    external_id: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")

        if not self.source_name.strip():
            raise ValueError("source_name must not be empty")

        if not self.title.strip():
            raise ValueError("title must not be empty")

        if self.external_id is not None and not self.external_id.strip():
            raise ValueError("external_id must not be blank")

        validate_http_url(
            self.source_url,
            field_name="source_url",
        )
        validate_http_url(
            self.canonical_url,
            field_name="canonical_url",
        )
        validate_aware_datetime(
            self.collected_at,
            field_name="collected_at",
        )

        if self.published_at is not None:
            validate_aware_datetime(
                self.published_at,
                field_name="published_at",
            )


@dataclass(frozen=True, slots=True)
class CollectionFailure:
    code: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Failure code must not be empty")

        if not self.message.strip():
            raise ValueError("Failure message must not be empty")


@dataclass(frozen=True, slots=True)
class CollectionResult:
    source: NewsSource
    status: CollectionStatus
    items: tuple[CollectedNewsItem, ...]
    started_at: datetime
    completed_at: datetime
    failure: CollectionFailure | None = None

    def __post_init__(self) -> None:
        validate_aware_datetime(
            self.started_at,
            field_name="started_at",
        )
        validate_aware_datetime(
            self.completed_at,
            field_name="completed_at",
        )

        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not be earlier than started_at")

        if self.status is CollectionStatus.SUCCEEDED:
            if not self.items:
                raise ValueError("A successful result must contain at least one item")

            if self.failure is not None:
                raise ValueError("A successful result must not contain a failure")

        elif self.status is CollectionStatus.EMPTY:
            if self.items:
                raise ValueError("An empty result must not contain items")

            if self.failure is not None:
                raise ValueError("An empty result must not contain a failure")

        elif self.status is CollectionStatus.FAILED:
            if self.items:
                raise ValueError("A failed result must not contain items")

            if self.failure is None:
                raise ValueError("A failed result must contain failure details")

        for item in self.items:
            if item.source_id != self.source.source_id:
                raise ValueError("Collected item source_id does not match the source")

    @property
    def duration_ms(self) -> int:
        duration = self.completed_at - self.started_at
        return int(duration.total_seconds() * 1000)

    @classmethod
    def succeeded(
        cls,
        *,
        source: NewsSource,
        items: tuple[CollectedNewsItem, ...],
        started_at: datetime,
        completed_at: datetime,
    ) -> "CollectionResult":
        return cls(
            source=source,
            status=CollectionStatus.SUCCEEDED,
            items=items,
            started_at=started_at,
            completed_at=completed_at,
        )

    @classmethod
    def empty(
        cls,
        *,
        source: NewsSource,
        started_at: datetime,
        completed_at: datetime,
    ) -> "CollectionResult":
        return cls(
            source=source,
            status=CollectionStatus.EMPTY,
            items=(),
            started_at=started_at,
            completed_at=completed_at,
        )

    @classmethod
    def failed(
        cls,
        *,
        source: NewsSource,
        failure: CollectionFailure,
        started_at: datetime,
        completed_at: datetime,
    ) -> "CollectionResult":
        return cls(
            source=source,
            status=CollectionStatus.FAILED,
            items=(),
            started_at=started_at,
            completed_at=completed_at,
            failure=failure,
        )

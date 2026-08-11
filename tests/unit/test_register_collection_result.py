from dataclasses import replace
from datetime import UTC, datetime

import pytest

from project_g.application.news import (
    INITIAL_NEWS_SOURCES,
)
from project_g.application.news.register_collected_item import (
    CollectedNewsRegistrationStatus,
    RegisterCollectedNewsItemResult,
)
from project_g.application.news.register_collection_result import (
    CollectionRegistrationFailedError,
    RegisterCollectionResult,
)
from project_g.domain.news import (
    CollectedNewsItem,
    CollectionFailure,
    CollectionResult,
    NewsSource,
    SourceStatus,
)

_STARTED_AT = datetime(
    2026,
    8,
    11,
    8,
    0,
    tzinfo=UTC,
)
_COMPLETED_AT = datetime(
    2026,
    8,
    11,
    8,
    0,
    1,
    tzinfo=UTC,
)


def _source() -> NewsSource:
    source = next(
        source for source in INITIAL_NEWS_SOURCES if source.source_id == "giants_official_news"
    )

    return replace(
        source,
        status=SourceStatus.ENABLED,
    )


def _item(
    article_id: str,
) -> CollectedNewsItem:
    url = f"https://www.giants.jp/news/{article_id}/"

    return CollectedNewsItem(
        source_id="giants_official_news",
        source_name="Giants Official News",
        title=f"Article {article_id}",
        source_url=url,
        canonical_url=url,
        collected_at=_COMPLETED_AT,
        published_at=_STARTED_AT,
        external_id=article_id,
    )


class FakeRegistrar:
    def __init__(
        self,
        duplicate_ids: set[str] | None = None,
    ) -> None:
        self.duplicate_ids = duplicate_ids or set()
        self.items: list[CollectedNewsItem] = []

    def execute(
        self,
        item: CollectedNewsItem,
    ) -> RegisterCollectedNewsItemResult:
        self.items.append(item)

        if item.external_id in self.duplicate_ids:
            status = CollectedNewsRegistrationStatus.DUPLICATE
        else:
            status = CollectedNewsRegistrationStatus.REGISTERED

        return RegisterCollectedNewsItemResult(
            status=status,
            canonical_url=item.canonical_url,
        )


def test_collection_registers_new_and_skips_duplicates() -> None:
    registrar = FakeRegistrar(duplicate_ids={"200"})

    result = CollectionResult.succeeded(
        source=_source(),
        items=(
            _item("100"),
            _item("200"),
            _item("300"),
        ),
        started_at=_STARTED_AT,
        completed_at=_COMPLETED_AT,
    )

    summary = RegisterCollectionResult(
        registrar=registrar,
    ).execute(result)

    assert summary.discovered_count == 3
    assert summary.registered_count == 2
    assert summary.duplicate_count == 1
    assert len(summary.registered_items) == 2
    assert len(registrar.items) == 3


def test_empty_collection_returns_empty_summary() -> None:
    summary = RegisterCollectionResult(
        registrar=FakeRegistrar(),
    ).execute(
        CollectionResult.empty(
            source=_source(),
            started_at=_STARTED_AT,
            completed_at=_COMPLETED_AT,
        )
    )

    assert summary.discovered_count == 0
    assert summary.registered_count == 0
    assert summary.duplicate_count == 0
    assert summary.registrations == ()


def test_failed_collection_is_rejected() -> None:
    result = CollectionResult.failed(
        source=_source(),
        failure=CollectionFailure(
            code="SOURCE_HTTP_STATUS",
            message="The source returned HTTP status 403",
            retryable=False,
        ),
        started_at=_STARTED_AT,
        completed_at=_COMPLETED_AT,
    )

    with pytest.raises(
        CollectionRegistrationFailedError,
        match="HTTP status 403",
    ):
        RegisterCollectionResult(
            registrar=FakeRegistrar(),
        ).execute(result)

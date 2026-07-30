from datetime import UTC, datetime, timedelta

import pytest

from project_g.domain.news import (
    CollectedNewsItem,
    CollectionFailure,
    CollectionRequest,
    CollectionResult,
    CollectionStatus,
    NewsSource,
    SourceStatus,
    SourceType,
)


def _source(
    *,
    source_id: str = "giants_official",
) -> NewsSource:
    return NewsSource(
        source_id=source_id,
        name="Giants Official",
        source_type=SourceType.WEBSITE,
        base_url="https://example.com/giants",
        is_official=True,
        priority=100,
    )


def _item(
    source: NewsSource,
) -> CollectedNewsItem:
    collected_at = datetime.now(UTC)

    return CollectedNewsItem(
        source_id=source.source_id,
        source_name=source.name,
        title="Giants news",
        source_url="https://example.com/giants/news/1",
        canonical_url="https://example.com/giants/news/1",
        published_at=collected_at - timedelta(minutes=5),
        collected_at=collected_at,
        external_id="news-1",
    )


def test_news_source_preserves_source_metadata() -> None:
    source = _source()

    assert source.source_type is SourceType.WEBSITE
    assert source.status is SourceStatus.ENABLED
    assert source.is_official is True
    assert source.collectable is True


@pytest.mark.parametrize(
    "source_id",
    [
        "",
        "A",
        "Giants Official",
        "giants.official",
    ],
)
def test_invalid_source_ids_are_rejected(
    source_id: str,
) -> None:
    with pytest.raises(ValueError):
        _source(source_id=source_id)


def test_collection_request_validates_timeout() -> None:
    with pytest.raises(ValueError):
        CollectionRequest(
            source=_source(),
            timeout_seconds=0,
        )


def test_successful_collection_preserves_provenance() -> None:
    source = _source()
    started_at = datetime.now(UTC)
    completed_at = started_at + timedelta(milliseconds=250)
    item = _item(source)

    result = CollectionResult.succeeded(
        source=source,
        items=(item,),
        started_at=started_at,
        completed_at=completed_at,
    )

    assert result.status is CollectionStatus.SUCCEEDED
    assert result.items == (item,)
    assert result.source.source_id == "giants_official"
    assert result.duration_ms == 250
    assert result.failure is None


def test_empty_collection_is_represented_explicitly() -> None:
    source = _source()
    now = datetime.now(UTC)

    result = CollectionResult.empty(
        source=source,
        started_at=now,
        completed_at=now,
    )

    assert result.status is CollectionStatus.EMPTY
    assert result.items == ()
    assert result.failure is None


def test_failed_collection_preserves_context() -> None:
    source = _source()
    now = datetime.now(UTC)
    failure = CollectionFailure(
        code="SOURCE_TIMEOUT",
        message="The source did not respond in time",
        retryable=True,
    )

    result = CollectionResult.failed(
        source=source,
        failure=failure,
        started_at=now,
        completed_at=now + timedelta(seconds=10),
    )

    assert result.status is CollectionStatus.FAILED
    assert result.source == source
    assert result.failure == failure
    assert result.failure.retryable is True


def test_item_from_another_source_is_rejected() -> None:
    source = _source()
    other_source = _source(source_id="other_source")
    now = datetime.now(UTC)

    with pytest.raises(
        ValueError,
        match="source_id does not match",
    ):
        CollectionResult.succeeded(
            source=source,
            items=(_item(other_source),),
            started_at=now,
            completed_at=now,
        )

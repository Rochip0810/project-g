from project_g.domain.news import (
    NewsSource,
    SourceStatus,
    SourceType,
)
from project_g.infrastructure.database.base import Base
from project_g.infrastructure.database.models import (
    NewsSourceRecord,
)


def _source() -> NewsSource:
    return NewsSource(
        source_id="giants_official",
        name="Giants Official",
        source_type=SourceType.WEBSITE,
        base_url="https://example.com/giants",
        is_official=True,
        status=SourceStatus.ENABLED,
        priority=100,
    )


def test_news_source_record_is_registered_in_metadata() -> None:
    assert "news_sources" in Base.metadata.tables


def test_news_source_record_round_trip() -> None:
    source = _source()

    record = NewsSourceRecord.from_domain(source)

    assert record.source_id == source.source_id
    assert record.source_type == "website"
    assert record.status == "enabled"
    assert record.to_domain() == source


def test_news_source_record_can_apply_domain_changes() -> None:
    source = _source()
    record = NewsSourceRecord.from_domain(source)

    updated = NewsSource(
        source_id=source.source_id,
        name="Updated Giants Official",
        source_type=SourceType.RSS,
        base_url="https://example.com/giants/rss",
        is_official=True,
        status=SourceStatus.PAUSED,
        priority=90,
    )

    record.apply_domain(updated)

    assert record.to_domain() == updated

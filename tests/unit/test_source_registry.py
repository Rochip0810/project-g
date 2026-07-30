import pytest

from project_g.application.news import (
    DuplicateNewsSourceError,
    NewsSourceNotFoundError,
    SourceRegistry,
)
from project_g.domain.news import (
    NewsSource,
    SourceStatus,
    SourceType,
)


def _source(
    source_id: str,
    *,
    official: bool,
    priority: int,
    status: SourceStatus = SourceStatus.ENABLED,
) -> NewsSource:
    return NewsSource(
        source_id=source_id,
        name=source_id.replace("_", " ").title(),
        source_type=SourceType.WEBSITE,
        base_url=f"https://example.com/{source_id}",
        is_official=official,
        priority=priority,
        status=status,
    )


def test_registry_rejects_duplicate_source_ids() -> None:
    source = _source(
        "giants_official",
        official=True,
        priority=100,
    )
    registry = SourceRegistry([source])

    with pytest.raises(DuplicateNewsSourceError):
        registry.register(source)


def test_registry_can_pause_disable_and_enable_sources() -> None:
    source = _source(
        "giants_official",
        official=True,
        priority=100,
    )
    registry = SourceRegistry([source])

    assert registry.pause(source.source_id).status is (SourceStatus.PAUSED)
    assert registry.disable(source.source_id).status is (SourceStatus.DISABLED)
    assert registry.enable(source.source_id).status is (SourceStatus.ENABLED)


def test_collectable_sources_prioritize_official_sources() -> None:
    unofficial = _source(
        "sports_news",
        official=False,
        priority=100,
    )
    official = _source(
        "giants_official",
        official=True,
        priority=80,
    )
    disabled = _source(
        "disabled_source",
        official=True,
        priority=100,
        status=SourceStatus.DISABLED,
    )

    registry = SourceRegistry([unofficial, disabled, official])

    assert registry.list_collectable() == (
        official,
        unofficial,
    )


def test_missing_source_raises_explicit_error() -> None:
    registry = SourceRegistry()

    with pytest.raises(NewsSourceNotFoundError):
        registry.get("missing_source")

from project_g.application.news import (
    INITIAL_NEWS_SOURCES,
)
from project_g.domain.news import SourceStatus


def test_initial_catalog_contains_seven_sources() -> None:
    assert len(INITIAL_NEWS_SOURCES) == 7


def test_initial_catalog_uses_expected_editorial_order() -> None:
    assert tuple(source.source_id for source in INITIAL_NEWS_SOURCES) == (
        "giants_official_news",
        "giants_official_schedule",
        "npb_official_schedule",
        "npb_official_stats",
        "hochi_giants_x",
        "hochi_giants_articles",
        "hochi_giants_instagram",
    )


def test_primary_sources_are_marked_as_official() -> None:
    official_source_ids = {
        source.source_id for source in INITIAL_NEWS_SOURCES if source.is_official
    }

    assert official_source_ids == {
        "giants_official_news",
        "giants_official_schedule",
        "npb_official_schedule",
        "npb_official_stats",
    }


def test_hochi_x_and_articles_are_enabled() -> None:
    sources = {source.source_id: source for source in INITIAL_NEWS_SOURCES}

    assert sources["hochi_giants_x"].status is (SourceStatus.ENABLED)
    assert sources["hochi_giants_articles"].status is (SourceStatus.ENABLED)


def test_hochi_instagram_is_paused() -> None:
    instagram = next(
        source for source in INITIAL_NEWS_SOURCES if source.source_id == "hochi_giants_instagram"
    )

    assert instagram.status is SourceStatus.PAUSED
    assert instagram.collectable is False


def test_catalog_priorities_are_unique_and_descending() -> None:
    priorities = tuple(source.priority for source in INITIAL_NEWS_SOURCES)

    assert len(set(priorities)) == 7
    assert priorities == tuple(sorted(priorities, reverse=True))

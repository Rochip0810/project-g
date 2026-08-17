import pytest

from project_g.interfaces.workers.jobs import (
    process_news_relevance,
)


def test_process_news_relevance_rejects_invalid_uuid() -> None:
    with pytest.raises(
        ValueError,
        match="Invalid news intake UUID",
    ):
        process_news_relevance("not-a-valid-uuid")


def test_recover_pending_news_relevance_rejects_invalid_limit() -> None:
    from project_g.interfaces.workers.jobs import (
        recover_pending_news_relevance,
    )

    with pytest.raises(
        ValueError,
        match="limit must be between 1 and 100",
    ):
        recover_pending_news_relevance(0)

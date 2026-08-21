import pytest

from project_g.interfaces.workers.jobs import (
    process_news_priority,
)


def test_process_news_priority_rejects_invalid_uuid() -> None:
    with pytest.raises(
        ValueError,
        match="Invalid news intake UUID",
    ):
        process_news_priority("not-a-valid-uuid")


def test_recover_pending_news_priority_rejects_invalid_limit() -> None:
    from project_g.interfaces.workers.jobs import (
        recover_pending_news_priority,
    )

    with pytest.raises(
        ValueError,
        match="limit must be between 1 and 100",
    ):
        recover_pending_news_priority(0)

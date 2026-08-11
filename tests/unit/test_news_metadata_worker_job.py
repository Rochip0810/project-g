import pytest

from project_g.interfaces.workers.jobs import (
    process_news_metadata,
    system_heartbeat,
)


def test_system_heartbeat_returns_ok() -> None:
    result = system_heartbeat("news-worker-test")

    assert result["status"] == "ok"
    assert result["source"] == "news-worker-test"
    assert "timestamp" in result


def test_process_news_metadata_rejects_invalid_uuid() -> None:
    with pytest.raises(
        ValueError,
        match="Invalid news intake UUID",
    ):
        process_news_metadata("not-a-valid-uuid")

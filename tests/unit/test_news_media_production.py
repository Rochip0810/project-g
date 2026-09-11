from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from project_g.domain.news.media_production import (
    InvalidNewsMediaProductionError,
    InvalidNewsMediaProductionTransitionError,
    NewsMediaProduction,
    NewsMediaProductionStatus,
)

_NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def _pending() -> NewsMediaProduction:
    return NewsMediaProduction.pending(
        media_production_id=uuid4(),
        script_generation_id=uuid4(),
        media_version=1,
        created_at=_NOW,
    )


def test_pending_factory_creates_initial_state() -> None:
    production = _pending()

    assert production.status is NewsMediaProductionStatus.PENDING
    assert production.media_version == 1
    assert production.attempt_count == 0
    assert production.failure_reason is None
    assert production.started_at is None
    assert production.completed_at is None
    assert production.created_at == _NOW
    assert production.updated_at == _NOW


def test_start_moves_pending_to_processing() -> None:
    started_at = _NOW + timedelta(minutes=1)

    production = _pending().start(
        started_at=started_at,
    )

    assert production.status is NewsMediaProductionStatus.PROCESSING
    assert production.attempt_count == 1
    assert production.failure_reason is None
    assert production.started_at == started_at
    assert production.completed_at is None
    assert production.updated_at == started_at


def test_processing_can_be_marked_ready() -> None:
    started_at = _NOW + timedelta(minutes=1)
    completed_at = _NOW + timedelta(minutes=2)

    production = _pending().start(started_at=started_at).mark_ready(completed_at=completed_at)

    assert production.status is NewsMediaProductionStatus.READY
    assert production.attempt_count == 1
    assert production.failure_reason is None
    assert production.completed_at == completed_at
    assert production.updated_at == completed_at


def test_failed_production_can_retry() -> None:
    first_start = _NOW + timedelta(minutes=1)
    failed_at = _NOW + timedelta(minutes=2)
    retry_at = _NOW + timedelta(minutes=3)

    failed = (
        _pending()
        .start(started_at=first_start)
        .mark_failed(
            reason="  renderer unavailable  ",
            completed_at=failed_at,
        )
    )

    assert failed.status is NewsMediaProductionStatus.FAILED
    assert failed.failure_reason == "renderer unavailable"
    assert failed.attempt_count == 1

    retried = failed.start(
        started_at=retry_at,
    )

    assert retried.status is NewsMediaProductionStatus.PROCESSING
    assert retried.attempt_count == 2
    assert retried.failure_reason is None
    assert retried.started_at == retry_at
    assert retried.completed_at is None
    assert retried.updated_at == retry_at


def test_ready_production_cannot_start_again() -> None:
    production = (
        _pending()
        .start(started_at=_NOW + timedelta(minutes=1))
        .mark_ready(completed_at=_NOW + timedelta(minutes=2))
    )

    with pytest.raises(
        InvalidNewsMediaProductionTransitionError,
        match="pending or failed",
    ):
        production.start(started_at=_NOW + timedelta(minutes=3))


def test_pending_rejects_invalid_media_version() -> None:
    with pytest.raises(
        InvalidNewsMediaProductionError,
        match="media_version",
    ):
        NewsMediaProduction.pending(
            media_production_id=uuid4(),
            script_generation_id=uuid4(),
            media_version=0,
            created_at=_NOW,
        )


def test_pending_rejects_naive_created_at() -> None:
    with pytest.raises(
        InvalidNewsMediaProductionError,
        match="created_at must be timezone-aware",
    ):
        NewsMediaProduction.pending(
            media_production_id=uuid4(),
            script_generation_id=uuid4(),
            media_version=1,
            created_at=datetime(2026, 9, 11, 12, 0),
        )


def test_start_rejects_time_before_current_state() -> None:
    with pytest.raises(
        InvalidNewsMediaProductionError,
        match="started_at must not be earlier than updated_at",
    ):
        _pending().start(
            started_at=_NOW - timedelta(seconds=1),
        )


def test_failed_state_requires_failure_reason() -> None:
    started_at = _NOW + timedelta(minutes=1)
    completed_at = _NOW + timedelta(minutes=2)

    with pytest.raises(
        InvalidNewsMediaProductionError,
        match="failed media production must include failure_reason",
    ):
        NewsMediaProduction(
            media_production_id=uuid4(),
            script_generation_id=uuid4(),
            media_version=1,
            status=NewsMediaProductionStatus.FAILED,
            attempt_count=1,
            failure_reason=None,
            created_at=_NOW,
            started_at=started_at,
            completed_at=completed_at,
            updated_at=completed_at,
        )

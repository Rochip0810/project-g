from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.enqueue_collected_item import (
    EnqueueRegisteredCollectedNewsItem,
    InvalidCollectedNewsRegistrationError,
)
from project_g.application.news.register_collected_item import (
    CollectedNewsRegistrationStatus,
    RegisterCollectedNewsItemResult,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)

_JOB_ID = UUID("88b9bcee-ae94-4ac5-97a9-e2055ee229e7")
_INTAKE_ID = UUID("65abe008-5356-467a-9876-9959828980d7")
_CREATED_AT = datetime(
    2026,
    8,
    11,
    7,
    30,
    tzinfo=UTC,
)
_URL = "https://www.giants.jp/news/123456/"


class FakeQueueProvider:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                QueueName,
                str,
                Sequence[JobArgument],
                str | None,
            ]
        ] = []

    def enqueue(
        self,
        queue_name: QueueName,
        function_path: str,
        *,
        args: Sequence[JobArgument] = (),
        kwargs: Mapping[str, JobArgument] | None = None,
        job_id: str | None = None,
        description: str | None = None,
    ) -> JobSnapshot:
        self.calls.append(
            (
                queue_name,
                function_path,
                args,
                job_id,
            )
        )

        return JobSnapshot(
            job_id=job_id or "generated",
            queue=queue_name,
            status="queued",
        )


def _processing_job() -> NewsProcessingJob:
    return NewsProcessingJob.pending(
        job_id=_JOB_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_registered_item_is_enqueued() -> None:
    provider = FakeQueueProvider()

    registration = RegisterCollectedNewsItemResult(
        status=(CollectedNewsRegistrationStatus.REGISTERED),
        canonical_url=_URL,
        processing_job=_processing_job(),
    )

    snapshot = EnqueueRegisteredCollectedNewsItem(
        queue_provider=provider,
    ).execute(registration)

    assert snapshot is not None
    assert snapshot.queue is QueueName.DEFAULT
    assert snapshot.status == "queued"

    assert provider.calls == [
        (
            QueueName.DEFAULT,
            ("project_g.interfaces.workers.jobs.process_news_metadata"),
            [str(_INTAKE_ID)],
            f"news-metadata-{_JOB_ID}",
        )
    ]


def test_duplicate_item_is_not_enqueued() -> None:
    provider = FakeQueueProvider()

    registration = RegisterCollectedNewsItemResult(
        status=(CollectedNewsRegistrationStatus.DUPLICATE),
        canonical_url=_URL,
    )

    snapshot = EnqueueRegisteredCollectedNewsItem(
        queue_provider=provider,
    ).execute(registration)

    assert snapshot is None
    assert provider.calls == []


def test_registered_item_without_job_is_rejected() -> None:
    provider = FakeQueueProvider()

    registration = RegisterCollectedNewsItemResult(
        status=(CollectedNewsRegistrationStatus.REGISTERED),
        canonical_url=_URL,
    )

    with pytest.raises(
        InvalidCollectedNewsRegistrationError,
        match="must include a processing job",
    ):
        EnqueueRegisteredCollectedNewsItem(
            queue_provider=provider,
        ).execute(registration)

    assert provider.calls == []

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.enqueue_metadata_processing import (
    NEWS_METADATA_WORKER_FUNCTION,
    EnqueueNewsMetadataProcessing,
    NewsProcessingJobNotPendingError,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)

_JOB_ID = UUID("d95af92c-83ea-4c13-9254-e2bec84487bf")
_INTAKE_ID = UUID("55656390-4ed3-42c8-a4a7-87e9fe202651")
_CREATED_AT = datetime(
    2026,
    8,
    10,
    8,
    0,
    tzinfo=UTC,
)


class FakeQueueProvider:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                QueueName,
                str,
                Sequence[JobArgument],
                Mapping[str, JobArgument] | None,
                str | None,
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
                kwargs,
                job_id,
                description,
            )
        )

        return JobSnapshot(
            job_id=job_id or "generated-job",
            queue=queue_name,
            status="queued",
        )


def _pending_job() -> NewsProcessingJob:
    return NewsProcessingJob.pending(
        job_id=_JOB_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_pending_processing_job_is_enqueued() -> None:
    provider = FakeQueueProvider()

    snapshot = EnqueueNewsMetadataProcessing(
        queue_provider=provider,
    ).execute(_pending_job())

    assert snapshot.job_id == (f"news-metadata-{_JOB_ID}")
    assert snapshot.queue is QueueName.DEFAULT
    assert snapshot.status == "queued"

    assert provider.calls == [
        (
            QueueName.DEFAULT,
            NEWS_METADATA_WORKER_FUNCTION,
            [str(_INTAKE_ID)],
            None,
            f"news-metadata-{_JOB_ID}",
            (f"Process news metadata for intake {_INTAKE_ID}"),
        )
    ]


def test_processing_job_cannot_be_enqueued_twice_after_start() -> None:
    provider = FakeQueueProvider()
    processing = _pending_job().start(
        started_at=_CREATED_AT,
    )

    with pytest.raises(NewsProcessingJobNotPendingError):
        EnqueueNewsMetadataProcessing(
            queue_provider=provider,
        ).execute(processing)

    assert provider.calls == []


def test_worker_function_path_is_importable() -> None:
    from importlib import import_module

    module_path, function_name = NEWS_METADATA_WORKER_FUNCTION.rsplit(
        ".",
        1,
    )

    module = import_module(module_path)
    function = getattr(
        module,
        function_name,
        None,
    )

    assert callable(function)

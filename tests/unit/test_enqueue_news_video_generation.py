from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast
from uuid import UUID

import pytest

from project_g.application.news.enqueue_news_video_generation import (
    EnqueueNewsVideoGeneration,
)
from project_g.application.news.prepare_news_video_jobs import (
    PreparedNewsVideoJob,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)

_VIDEO_ID = UUID("11111111-1111-4111-8111-000000000501")
_MEDIA_ID = UUID("11111111-1111-4111-8111-000000000301")


def _job() -> PreparedNewsVideoJob:
    return PreparedNewsVideoJob(
        video_generation_id=_VIDEO_ID,
        media_production_id=_MEDIA_ID,
        video_version=1,
        next_attempt_number=1,
    )


class FakeQueueProvider:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                QueueName,
                str,
                tuple[JobArgument, ...],
                Mapping[str, JobArgument] | None,
                str | None,
                str | None,
            ]
        ] = []

        self.snapshot = cast(JobSnapshot, object())

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
                tuple(args),
                kwargs,
                job_id,
                description,
            )
        )

        return self.snapshot


def test_enqueue_uses_correct_worker_and_arguments() -> None:
    queue = FakeQueueProvider()
    enqueue = EnqueueNewsVideoGeneration(
        queue_provider=queue,
    )

    result = enqueue.execute(_job())

    assert result is queue.snapshot

    assert queue.calls == [
        (
            QueueName.DEFAULT,
            "project_g.interfaces.workers.jobs.process_news_video",
            (str(_VIDEO_ID),),
            None,
            f"news-video-{_VIDEO_ID}-a1",
            "Generate Project G news video",
        )
    ]


def test_enqueue_same_attempt_uses_deterministic_job_id() -> None:
    queue = FakeQueueProvider()
    enqueue = EnqueueNewsVideoGeneration(
        queue_provider=queue,
    )

    enqueue.execute(_job())
    enqueue.execute(_job())

    assert len(queue.calls) == 2

    first_job_id = queue.calls[0][4]
    second_job_id = queue.calls[1][4]

    assert first_job_id == second_job_id
    assert first_job_id == f"news-video-{_VIDEO_ID}-a1"


def test_retry_uses_new_job_id_and_same_generation_id() -> None:
    queue = FakeQueueProvider()
    enqueue = EnqueueNewsVideoGeneration(
        queue_provider=queue,
    )

    first = _job()

    retry = replace(
        first,
        next_attempt_number=2,
    )

    enqueue.execute(first)
    enqueue.execute(retry)

    assert len(queue.calls) == 2

    assert queue.calls[0][4] == f"news-video-{_VIDEO_ID}-a1"
    assert queue.calls[1][4] == f"news-video-{_VIDEO_ID}-a2"

    assert queue.calls[0][2] == (str(_VIDEO_ID),)
    assert queue.calls[1][2] == (str(_VIDEO_ID),)


def test_enqueue_rejects_invalid_video_version() -> None:
    queue = FakeQueueProvider()
    enqueue = EnqueueNewsVideoGeneration(
        queue_provider=queue,
    )

    invalid_job = replace(
        _job(),
        video_version=0,
    )

    with pytest.raises(
        ValueError,
        match="video_version must be at least 1",
    ):
        enqueue.execute(invalid_job)

    assert queue.calls == []


def test_enqueue_rejects_invalid_attempt_number() -> None:
    queue = FakeQueueProvider()
    enqueue = EnqueueNewsVideoGeneration(
        queue_provider=queue,
    )

    invalid_job = replace(
        _job(),
        next_attempt_number=0,
    )

    with pytest.raises(
        ValueError,
        match="next_attempt_number must be at least 1",
    ):
        enqueue.execute(invalid_job)

    assert queue.calls == []

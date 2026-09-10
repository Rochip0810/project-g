from collections.abc import Mapping, Sequence
from uuid import UUID

import pytest

from project_g.application.news.enqueue_news_script_generation import (
    EnqueueNewsScriptGeneration,
)
from project_g.application.news.select_news_script_enqueue_candidates import (
    NewsScriptEnqueueCandidate,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)

_INTAKE_ID = UUID("00000000-0000-0000-0000-000000000001")


class FakeQueueProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
            {
                "queue_name": queue_name,
                "function_path": function_path,
                "args": tuple(args),
                "kwargs": (dict(kwargs) if kwargs is not None else None),
                "job_id": job_id,
                "description": description,
            }
        )

        assert job_id is not None

        return JobSnapshot(
            job_id=job_id,
            queue=queue_name,
            status="queued",
        )


def test_enqueues_script_generation_with_preserved_ranking_score() -> None:
    queue_provider = FakeQueueProvider()
    service = EnqueueNewsScriptGeneration(
        queue_provider=queue_provider,
    )

    candidate = NewsScriptEnqueueCandidate(
        intake_id=_INTAKE_ID,
        generation_version=1,
        ranking_score=87,
    )

    result = service.execute(
        candidate,
        time_bucket=12345,
    )

    assert result.job_id == ("news-script-00000000-0000-0000-0000-000000000001-v1-b12345")

    assert queue_provider.calls == [
        {
            "queue_name": QueueName.DEFAULT,
            "function_path": ("project_g.interfaces.workers.jobs.process_news_script"),
            "args": (
                str(_INTAKE_ID),
                87,
            ),
            "kwargs": None,
            "job_id": ("news-script-00000000-0000-0000-0000-000000000001-v1-b12345"),
            "description": "Generate Project G news script",
        }
    ]


@pytest.mark.parametrize(
    "time_bucket",
    [-1],
)
def test_rejects_invalid_time_bucket(
    time_bucket: int,
) -> None:
    service = EnqueueNewsScriptGeneration(
        queue_provider=FakeQueueProvider(),
    )

    with pytest.raises(ValueError):
        service.execute(
            NewsScriptEnqueueCandidate(
                intake_id=_INTAKE_ID,
                generation_version=1,
                ranking_score=87,
            ),
            time_bucket=time_bucket,
        )


def test_rejects_unsupported_generation_version() -> None:
    service = EnqueueNewsScriptGeneration(
        queue_provider=FakeQueueProvider(),
    )

    with pytest.raises(ValueError):
        service.execute(
            NewsScriptEnqueueCandidate(
                intake_id=_INTAKE_ID,
                generation_version=2,
                ranking_score=87,
            ),
            time_bucket=12345,
        )

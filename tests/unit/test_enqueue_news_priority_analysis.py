from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.enqueue_priority_analysis import (
    NEWS_PRIORITY_WORKER_FUNCTION,
    EnqueueNewsPriorityAnalysis,
    NewsPriorityAnalysisNotPendingError,
)
from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)

_ANALYSIS_ID = UUID("6edff033-b854-47c0-a3bf-b627688fb89d")
_INTAKE_ID = UUID("4b8eab24-cf9e-40bb-8aac-dc2760a81529")
_CREATED_AT = datetime(
    2026,
    8,
    21,
    7,
    0,
    tzinfo=UTC,
)


class FakeQueueProvider:
    def __init__(self) -> None:
        self.queue_name: QueueName | None = None
        self.function_path: str | None = None
        self.args: Sequence[JobArgument] = ()
        self.kwargs: Mapping[str, JobArgument] | None = None
        self.job_id: str | None = None
        self.description: str | None = None

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
        self.queue_name = queue_name
        self.function_path = function_path
        self.args = args
        self.kwargs = kwargs
        self.job_id = job_id
        self.description = description

        return JobSnapshot(
            job_id=job_id or "generated-job-id",
            queue=queue_name,
            status="queued",
        )


def _pending_analysis() -> NewsPriorityAnalysis:
    return NewsPriorityAnalysis.pending(
        analysis_id=_ANALYSIS_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    )


def test_pending_analysis_is_enqueued() -> None:
    provider = FakeQueueProvider()

    service = EnqueueNewsPriorityAnalysis(queue_provider=provider)

    snapshot = service.execute(_pending_analysis())

    assert provider.queue_name is QueueName.DEFAULT
    assert provider.function_path == NEWS_PRIORITY_WORKER_FUNCTION
    assert provider.args == [str(_INTAKE_ID)]
    assert provider.job_id == (f"news-priority-{_ANALYSIS_ID}")
    assert snapshot.status == "queued"


def test_analyzed_analysis_cannot_be_enqueued() -> None:
    analysis = _pending_analysis().record_analyzed(
        priority_score=88,
        reason="High editorial value.",
        updated_at=_CREATED_AT,
    )

    service = EnqueueNewsPriorityAnalysis(queue_provider=FakeQueueProvider())

    with pytest.raises(
        NewsPriorityAnalysisNotPendingError,
    ):
        service.execute(analysis)

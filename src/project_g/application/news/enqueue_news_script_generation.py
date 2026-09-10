from collections.abc import Mapping, Sequence
from typing import Protocol

from project_g.application.news.select_news_script_enqueue_candidates import (
    NewsScriptEnqueueCandidate,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)


class NewsScriptQueueProvider(Protocol):
    def enqueue(
        self,
        queue_name: QueueName,
        function_path: str,
        *,
        args: Sequence[JobArgument] = (),
        kwargs: Mapping[str, JobArgument] | None = None,
        job_id: str | None = None,
        description: str | None = None,
    ) -> JobSnapshot: ...


class EnqueueNewsScriptGeneration:
    def __init__(
        self,
        *,
        queue_provider: NewsScriptQueueProvider,
    ) -> None:
        self._queue_provider = queue_provider

    def execute(
        self,
        candidate: NewsScriptEnqueueCandidate,
        *,
        time_bucket: int,
    ) -> JobSnapshot:
        if candidate.generation_version != 1:
            raise ValueError("only generation_version=1 is currently supported")

        if time_bucket < 0:
            raise ValueError("time_bucket must be non-negative")

        job_id = f"news-script-{candidate.intake_id}-v{candidate.generation_version}-b{time_bucket}"

        return self._queue_provider.enqueue(
            QueueName.DEFAULT,
            "project_g.interfaces.workers.jobs.process_news_script",
            args=(
                str(candidate.intake_id),
                candidate.ranking_score,
            ),
            job_id=job_id,
            description="Generate Project G news script",
        )

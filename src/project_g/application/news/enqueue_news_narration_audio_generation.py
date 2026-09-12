from collections.abc import Mapping, Sequence
from typing import Protocol

from project_g.application.news.prepare_news_narration_audio_jobs import (
    PreparedNewsNarrationAudioJob,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)


class NewsNarrationAudioQueueProvider(Protocol):
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


class EnqueueNewsNarrationAudioGeneration:
    def __init__(
        self,
        *,
        queue_provider: NewsNarrationAudioQueueProvider,
    ) -> None:
        self._queue_provider = queue_provider

    def execute(
        self,
        job: PreparedNewsNarrationAudioJob,
    ) -> JobSnapshot:
        if job.audio_version < 1:
            raise ValueError("audio_version must be at least 1")

        if job.next_attempt_number < 1:
            raise ValueError("next_attempt_number must be at least 1")

        job_id = f"news-narration-audio-{job.audio_generation_id}-a{job.next_attempt_number}"

        return self._queue_provider.enqueue(
            QueueName.DEFAULT,
            ("project_g.interfaces.workers.jobs.process_news_narration_audio"),
            args=(str(job.audio_generation_id),),
            job_id=job_id,
            description="Generate Project G narration audio",
        )

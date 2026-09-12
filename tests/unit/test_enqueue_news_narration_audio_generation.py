from collections.abc import Mapping, Sequence
from uuid import UUID

import pytest

from project_g.application.news.enqueue_news_narration_audio_generation import (
    EnqueueNewsNarrationAudioGeneration,
)
from project_g.application.news.prepare_news_narration_audio_jobs import (
    PreparedNewsNarrationAudioJob,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)

_AUDIO_ID = UUID("836202eb-b6df-4277-926b-320084822101")
_MEDIA_ID = UUID("836202eb-b6df-4277-926b-320084822201")


class FakeQueueProvider:
    def __init__(self) -> None:
        self.queue_name: QueueName | None = None
        self.function_path: str | None = None
        self.args: tuple[JobArgument, ...] = ()
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
        self.args = tuple(args)
        self.kwargs = kwargs
        self.job_id = job_id
        self.description = description

        return JobSnapshot(
            job_id=job_id or "generated-job-id",
            queue=queue_name,
            status="queued",
        )


def _job(
    *,
    audio_version: int = 1,
    next_attempt_number: int = 1,
) -> PreparedNewsNarrationAudioJob:
    return PreparedNewsNarrationAudioJob(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=audio_version,
        next_attempt_number=next_attempt_number,
    )


def test_enqueue_uses_deterministic_attempt_job_id() -> None:
    queue_provider = FakeQueueProvider()

    snapshot = EnqueueNewsNarrationAudioGeneration(queue_provider=queue_provider).execute(
        _job(
            next_attempt_number=2,
        )
    )

    expected_job_id = f"news-narration-audio-{_AUDIO_ID}-a2"

    assert snapshot.job_id == expected_job_id
    assert queue_provider.queue_name is QueueName.DEFAULT
    assert queue_provider.function_path == (
        "project_g.interfaces.workers.jobs.process_news_narration_audio"
    )
    assert queue_provider.args == (str(_AUDIO_ID),)
    assert queue_provider.kwargs is None
    assert queue_provider.job_id == expected_job_id
    assert queue_provider.description == ("Generate Project G narration audio")


def test_enqueue_attempt_changes_job_id() -> None:
    queue_provider = FakeQueueProvider()
    service = EnqueueNewsNarrationAudioGeneration(queue_provider=queue_provider)

    first = service.execute(_job(next_attempt_number=1))
    second = service.execute(_job(next_attempt_number=2))

    assert first.job_id != second.job_id
    assert first.job_id.endswith("-a1")
    assert second.job_id.endswith("-a2")


@pytest.mark.parametrize(
    ("audio_version", "next_attempt_number"),
    (
        (0, 1),
        (1, 0),
    ),
)
def test_enqueue_rejects_invalid_job(
    audio_version: int,
    next_attempt_number: int,
) -> None:
    queue_provider = FakeQueueProvider()

    with pytest.raises(ValueError):
        EnqueueNewsNarrationAudioGeneration(queue_provider=queue_provider).execute(
            _job(
                audio_version=audio_version,
                next_attempt_number=(next_attempt_number),
            )
        )

    assert queue_provider.job_id is None

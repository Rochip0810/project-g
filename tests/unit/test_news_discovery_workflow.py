from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from project_g.application.news import (
    INITIAL_NEWS_SOURCES,
)
from project_g.application.news.register_collected_item import (
    CollectedNewsRegistrationStatus,
    RegisterCollectedNewsItemResult,
)
from project_g.application.news.register_collection_result import (
    RegisterCollectionResultSummary,
)
from project_g.domain.news import (
    CollectedNewsItem,
    CollectionFailure,
    CollectionRequest,
    CollectionResult,
    NewsSource,
    SourceStatus,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.ports.queue import (
    JobArgument,
    JobSnapshot,
    QueueName,
)
from project_g.workflows.news_discovery import (
    NewsDiscoveryWorkflow,
)

_NOW = datetime(
    2026,
    8,
    11,
    8,
    30,
    tzinfo=UTC,
)

_INTAKE_ID = UUID("e947f510-e171-44f5-8f86-e55929aba605")

_JOB_ID = UUID("acaf02f1-bb65-41d2-b804-a1d5fcb0b88c")


def _source() -> NewsSource:
    source = next(
        source for source in INITIAL_NEWS_SOURCES if source.source_id == "giants_official_news"
    )

    return replace(
        source,
        status=SourceStatus.ENABLED,
    )


def _item() -> CollectedNewsItem:
    url = "https://www.giants.jp/news/123456/"

    return CollectedNewsItem(
        source_id="giants_official_news",
        source_name="Giants Official News",
        title="Test article",
        source_url=url,
        canonical_url=url,
        collected_at=_NOW,
        published_at=_NOW,
        external_id="123456",
    )


class FakeCollector:
    def __init__(
        self,
        result: CollectionResult,
    ) -> None:
        self._result = result

    @property
    def source(self) -> NewsSource:
        return self._result.source

    def collect(
        self,
        request: CollectionRequest,
    ) -> CollectionResult:
        assert request.source.source_id == (self.source.source_id)
        return self._result


class FakeRegistrationRunner:
    def __init__(
        self,
        summary: RegisterCollectionResultSummary,
    ) -> None:
        self.summary = summary
        self.called = False
        self.committed = False

    def execute(
        self,
        result: CollectionResult,
    ) -> RegisterCollectionResultSummary:
        self.called = True

        assert result.status.value == "succeeded"

        # Represents the DB transaction having committed
        # before control returns to the workflow.
        self.committed = True

        return self.summary


class FakeQueueProvider:
    def __init__(
        self,
        registration_runner: FakeRegistrationRunner,
    ) -> None:
        self.registration_runner = registration_runner
        self.calls: list[str] = []

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
        assert self.registration_runner.committed
        assert queue_name is QueueName.DEFAULT

        self.calls.append(function_path)

        return JobSnapshot(
            job_id=job_id or "generated",
            queue=queue_name,
            status="queued",
        )


def test_successful_collection_commits_before_queueing() -> None:
    source = _source()

    collection = CollectionResult.succeeded(
        source=source,
        items=(_item(),),
        started_at=_NOW,
        completed_at=_NOW,
    )

    processing_job = NewsProcessingJob.pending(
        job_id=_JOB_ID,
        intake_id=_INTAKE_ID,
        created_at=_NOW,
    )

    registration = RegisterCollectedNewsItemResult(
        status=(CollectedNewsRegistrationStatus.REGISTERED),
        canonical_url=("https://www.giants.jp/news/123456/"),
        processing_job=processing_job,
    )

    summary = RegisterCollectionResultSummary(
        source_id=source.source_id,
        discovered_count=1,
        registered_count=1,
        duplicate_count=0,
        registrations=(registration,),
    )

    runner = FakeRegistrationRunner(summary)
    queue_provider = FakeQueueProvider(runner)

    result = NewsDiscoveryWorkflow(
        collector=FakeCollector(collection),
        registration_runner=runner,
        queue_provider=queue_provider,
    ).execute(
        timeout_seconds=10,
        max_items=5,
    )

    assert runner.called
    assert runner.committed
    assert result.registration is not None
    assert result.registration.registered_count == 1
    assert result.queued_count == 1
    assert len(queue_provider.calls) == 1


def test_failed_collection_does_not_touch_database_or_queue() -> None:
    source = _source()

    collection = CollectionResult.failed(
        source=source,
        failure=CollectionFailure(
            code="SOURCE_HTTP_STATUS",
            message="HTTP 403",
            retryable=False,
        ),
        started_at=_NOW,
        completed_at=_NOW,
    )

    summary = RegisterCollectionResultSummary(
        source_id=source.source_id,
        discovered_count=0,
        registered_count=0,
        duplicate_count=0,
        registrations=(),
    )

    runner = FakeRegistrationRunner(summary)
    queue_provider = FakeQueueProvider(runner)

    result = NewsDiscoveryWorkflow(
        collector=FakeCollector(collection),
        registration_runner=runner,
        queue_provider=queue_provider,
    ).execute(
        timeout_seconds=10,
        max_items=5,
    )

    assert not runner.called
    assert result.registration is None
    assert result.queue_jobs == ()
    assert queue_provider.calls == []

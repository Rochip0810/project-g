from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from project_g.application.news.enqueue_collected_item import (
    EnqueueRegisteredCollectedNewsItem,
)
from project_g.application.news.initial_sources import (
    INITIAL_NEWS_SOURCES,
)
from project_g.application.news.manual_url import (
    ManualNewsUrlResolver,
)
from project_g.application.news.register_collected_item import (
    RegisterCollectedNewsItem,
)
from project_g.application.news.register_collection_result import (
    RegisterCollectionResult,
    RegisterCollectionResultSummary,
)
from project_g.domain.news import (
    CollectionRequest,
    CollectionResult,
    CollectionStatus,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsArticleMetadataRepository,
    SqlAlchemyNewsProcessingJobRepository,
)
from project_g.ports import NewsCollector
from project_g.ports.queue import (
    JobSnapshot,
    QueueProvider,
)


class CollectionRegistrationRunner(Protocol):
    def execute(
        self,
        result: CollectionResult,
    ) -> RegisterCollectionResultSummary: ...


class SqlAlchemyCollectionRegistrationRunner:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._session_factory = session_factory

    def execute(
        self,
        result: CollectionResult,
    ) -> RegisterCollectionResultSummary:
        with self._session_factory.begin() as session:
            registrar = RegisterCollectedNewsItem(
                resolver=ManualNewsUrlResolver(INITIAL_NEWS_SOURCES),
                intake_repository=(SqlAlchemyManualNewsIntakeRepository(session)),
                processing_job_repository=(SqlAlchemyNewsProcessingJobRepository(session)),
                metadata_repository=(SqlAlchemyNewsArticleMetadataRepository(session)),
            )

            return RegisterCollectionResult(
                registrar=registrar,
            ).execute(result)


@dataclass(frozen=True, slots=True)
class NewsDiscoveryWorkflowResult:
    collection: CollectionResult
    registration: RegisterCollectionResultSummary | None
    queue_jobs: tuple[JobSnapshot, ...]

    @property
    def queued_count(self) -> int:
        return len(self.queue_jobs)


class NewsDiscoveryWorkflow:
    def __init__(
        self,
        *,
        collector: NewsCollector,
        registration_runner: CollectionRegistrationRunner,
        queue_provider: QueueProvider,
    ) -> None:
        self._collector = collector
        self._registration_runner = registration_runner
        self._queue_provider = queue_provider

    def execute(
        self,
        *,
        timeout_seconds: float,
        max_items: int,
    ) -> NewsDiscoveryWorkflowResult:
        collection = self._collector.collect(
            CollectionRequest(
                source=self._collector.source,
                timeout_seconds=timeout_seconds,
                max_items=max_items,
            )
        )

        if collection.status is CollectionStatus.FAILED:
            return NewsDiscoveryWorkflowResult(
                collection=collection,
                registration=None,
                queue_jobs=(),
            )

        registration = self._registration_runner.execute(collection)

        enqueuer = EnqueueRegisteredCollectedNewsItem(
            queue_provider=self._queue_provider,
        )

        queue_jobs: list[JobSnapshot] = []

        for registered_item in registration.registered_items:
            snapshot = enqueuer.execute(registered_item)

            if snapshot is None:
                raise RuntimeError("Registered news item was unexpectedly not enqueued")

            queue_jobs.append(snapshot)

        return NewsDiscoveryWorkflowResult(
            collection=collection,
            registration=registration,
            queue_jobs=tuple(queue_jobs),
        )

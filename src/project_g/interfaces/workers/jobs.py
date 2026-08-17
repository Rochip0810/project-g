from datetime import UTC, datetime
from uuid import UUID

from redis import Redis
from rq.exceptions import DuplicateJobError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from project_g.application.news.analyze_relevance import AnalyzeNewsRelevance
from project_g.application.news.enqueue_relevance_analysis import EnqueueNewsRelevanceAnalysis
from project_g.domain.news.article_metadata import NewsMetadataStatus
from project_g.domain.news.relevance_analysis import NewsRelevanceStatus
from project_g.infrastructure.ai.openai_relevance import OpenAIRelevanceAnalyzer
from project_g.infrastructure.collectors import (
    GiantsOfficialNewsCollector,
    GiantsOfficialNewsParser,
    HochiGiantsArticlesCollector,
    HochiGiantsArticlesParser,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    create_database_engine,
)
from project_g.infrastructure.database.models import (
    NewsArticleMetadataRecord,
    NewsRelevanceAnalysisRecord,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsArticleMetadataRepository,
    SqlAlchemyNewsRelevanceAnalysisRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.infrastructure.http import HttpxHttpClient
from project_g.infrastructure.queue import (
    RQQueueProvider,
    create_redis_connection_pool,
)
from project_g.interfaces.management.enrich_news_metadata import (
    enrich_news_metadata,
)
from project_g.workflows.news_discovery import (
    NewsDiscoveryWorkflow,
    SqlAlchemyCollectionRegistrationRunner,
)


def system_heartbeat(
    source: str = "worker",
) -> dict[str, str]:
    return {
        "status": "ok",
        "source": source,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def process_news_metadata(
    intake_id: str,
) -> dict[str, str]:
    """Process metadata and enqueue relevance analysis after commit."""
    try:
        parsed_intake_id = UUID(intake_id)
    except ValueError as error:
        raise ValueError(f"Invalid news intake UUID: {intake_id}") from error

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    relevance_analysis = None

    try:
        with factory.begin() as session:
            result = enrich_news_metadata(
                session=session,
                settings=settings,
                intake_id=parsed_intake_id,
            )

            if result.metadata.status is NewsMetadataStatus.EXTRACTED:
                relevance_repository = SqlAlchemyNewsRelevanceAnalysisRepository(session)
                relevance_analysis = relevance_repository.get_by_intake_id(parsed_intake_id)

                if relevance_analysis is None:
                    raise RuntimeError(
                        f"Relevance analysis was not found for intake: {parsed_intake_id}"
                    )

        relevance_queue_status = "skipped"
        relevance_job_id = ""

        if (
            relevance_analysis is not None
            and relevance_analysis.status is NewsRelevanceStatus.PENDING
        ):
            connection_pool = create_redis_connection_pool(
                settings,
                decode_responses=False,
            )
            connection = Redis.from_pool(connection_pool)

            try:
                queue_provider = RQQueueProvider(
                    settings,
                    connection,
                )

                snapshot = EnqueueNewsRelevanceAnalysis(queue_provider=queue_provider).execute(
                    relevance_analysis
                )

                relevance_queue_status = snapshot.status
                relevance_job_id = snapshot.job_id
            finally:
                connection.close()
                connection_pool.close()
        elif relevance_analysis is not None:
            relevance_queue_status = "already_processed"

        return {
            "status": "processed",
            "intake_id": str(result.metadata.intake_id),
            "metadata_status": result.metadata.status.value,
            "processing_status": (result.processing_job.status.value),
            "relevance_queue_status": (relevance_queue_status),
            "relevance_job_id": relevance_job_id,
        }

    finally:
        engine.dispose()


def process_news_relevance(
    intake_id: str,
) -> dict[str, str | int]:
    """Analyze one queued news item for Giants relevance."""
    try:
        parsed_intake_id = UUID(intake_id)
    except ValueError as error:
        raise ValueError(f"Invalid news intake UUID: {intake_id}") from error

    settings = Settings()

    analyzer = OpenAIRelevanceAnalyzer(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_relevance_model,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )

    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    try:
        with factory.begin() as session:
            service = AnalyzeNewsRelevance(
                intake_repository=(SqlAlchemyManualNewsIntakeRepository(session)),
                metadata_repository=(SqlAlchemyNewsArticleMetadataRepository(session)),
                relevance_repository=(SqlAlchemyNewsRelevanceAnalysisRepository(session)),
                analyzer=analyzer,
            )

            result = service.execute(parsed_intake_id)
    finally:
        engine.dispose()

    decision = result.analysis.decision

    if decision is None:
        raise RuntimeError("Analyzed relevance result has no decision")

    return {
        "status": "processed",
        "intake_id": str(result.analysis.intake_id),
        "relevance_status": result.analysis.status.value,
        "relevance_score": (result.analyzer_result.relevance_score),
        "decision": decision.value,
    }


def recover_pending_news_relevance(
    limit: int = 20,
) -> dict[str, str | int]:
    """Re-enqueue ready relevance analyses left pending."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    try:
        with factory() as session:
            statement = (
                select(NewsRelevanceAnalysisRecord)
                .join(
                    NewsArticleMetadataRecord,
                    NewsArticleMetadataRecord.intake_id == NewsRelevanceAnalysisRecord.intake_id,
                )
                .where(
                    NewsRelevanceAnalysisRecord.status == NewsRelevanceStatus.PENDING.value,
                    NewsArticleMetadataRecord.status.in_(
                        [
                            NewsMetadataStatus.EXTRACTED.value,
                            NewsMetadataStatus.MANUAL.value,
                        ]
                    ),
                )
                .order_by(
                    NewsRelevanceAnalysisRecord.updated_at.asc(),
                    NewsRelevanceAnalysisRecord.analysis_id.asc(),
                )
                .limit(limit)
            )

            records = session.scalars(statement).all()

            analyses = [record.to_domain() for record in records]

        connection_pool = create_redis_connection_pool(
            settings,
            decode_responses=False,
        )
        connection = Redis.from_pool(connection_pool)

        enqueued_count = 0
        duplicate_count = 0

        try:
            queue_provider = RQQueueProvider(
                settings,
                connection,
            )
            service = EnqueueNewsRelevanceAnalysis(queue_provider=queue_provider)

            for analysis in analyses:
                try:
                    service.execute(analysis)
                except DuplicateJobError:
                    duplicate_count += 1
                else:
                    enqueued_count += 1
        finally:
            connection.close()
            connection_pool.close()

        return {
            "status": "processed",
            "scanned_count": len(analyses),
            "enqueued_count": enqueued_count,
            "duplicate_count": duplicate_count,
        }

    finally:
        engine.dispose()


def discover_giants_news(
    max_items: int = 20,
) -> dict[str, str | int]:
    """Discover Giants news and enqueue new metadata jobs."""
    if not 1 <= max_items <= 50:
        raise ValueError("max_items must be between 1 and 50")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    connection_pool = create_redis_connection_pool(
        settings,
        decode_responses=False,
    )
    connection = Redis.from_pool(connection_pool)

    try:
        with factory() as session:
            source_repository = SqlAlchemyNewsSourceRepository(session)
            source = source_repository.get_by_source_id("giants_official_news")

        if source is None:
            return {
                "status": "source_missing",
                "source_id": "giants_official_news",
            }

        if not source.collectable:
            return {
                "status": "skipped",
                "source_id": source.source_id,
                "reason": "source_not_collectable",
            }

        collector = GiantsOfficialNewsCollector(
            source=source,
            http_client=HttpxHttpClient(
                user_agent=settings.collection_user_agent,
                max_redirects=settings.collection_max_redirects,
            ),
            parser=GiantsOfficialNewsParser(),
            max_response_bytes=(settings.collection_max_response_bytes),
        )

        queue_provider = RQQueueProvider(
            settings,
            connection,
        )

        workflow = NewsDiscoveryWorkflow(
            collector=collector,
            registration_runner=(
                SqlAlchemyCollectionRegistrationRunner(
                    session_factory=factory,
                )
            ),
            queue_provider=queue_provider,
        )

        result = workflow.execute(
            timeout_seconds=(settings.collection_request_timeout_seconds),
            max_items=max_items,
        )

        if result.registration is None:
            failure = result.collection.failure

            return {
                "status": "collection_failed",
                "source_id": source.source_id,
                "failure_code": (failure.code if failure is not None else "unknown"),
            }

        return {
            "status": "processed",
            "source_id": source.source_id,
            "discovered_count": (result.registration.discovered_count),
            "registered_count": (result.registration.registered_count),
            "duplicate_count": (result.registration.duplicate_count),
            "queued_count": result.queued_count,
        }
    finally:
        connection.close()
        connection_pool.close()
        engine.dispose()


def discover_hochi_giants_news(
    max_items: int = 5,
) -> dict[str, str | int]:
    """Discover Sports Hochi Giants articles and enqueue new metadata jobs."""
    if not 1 <= max_items <= 50:
        raise ValueError("max_items must be between 1 and 50")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    connection_pool = create_redis_connection_pool(
        settings,
        decode_responses=False,
    )
    connection = Redis.from_pool(connection_pool)

    try:
        with factory() as session:
            source_repository = SqlAlchemyNewsSourceRepository(session)
            source = source_repository.get_by_source_id("hochi_giants_articles")

        if source is None:
            return {
                "status": "source_missing",
                "source_id": "hochi_giants_articles",
            }

        if not source.collectable:
            return {
                "status": "skipped",
                "source_id": source.source_id,
                "reason": "source_not_collectable",
            }

        collector = HochiGiantsArticlesCollector(
            source=source,
            http_client=HttpxHttpClient(
                user_agent=settings.collection_user_agent,
                max_redirects=settings.collection_max_redirects,
            ),
            parser=HochiGiantsArticlesParser(),
            max_response_bytes=settings.collection_max_response_bytes,
        )

        queue_provider = RQQueueProvider(
            settings,
            connection,
        )

        workflow = NewsDiscoveryWorkflow(
            collector=collector,
            registration_runner=(
                SqlAlchemyCollectionRegistrationRunner(
                    session_factory=factory,
                )
            ),
            queue_provider=queue_provider,
        )

        result = workflow.execute(
            timeout_seconds=(settings.collection_request_timeout_seconds),
            max_items=max_items,
        )

        if result.registration is None:
            failure = result.collection.failure

            return {
                "status": "collection_failed",
                "source_id": source.source_id,
                "failure_code": (failure.code if failure is not None else "unknown"),
            }

        return {
            "status": "processed",
            "source_id": source.source_id,
            "discovered_count": (result.registration.discovered_count),
            "registered_count": (result.registration.registered_count),
            "duplicate_count": (result.registration.duplicate_count),
            "queued_count": result.queued_count,
        }
    finally:
        connection.close()
        connection_pool.close()
        engine.dispose()

from datetime import UTC, datetime
from uuid import UUID

from redis import Redis
from sqlalchemy.orm import sessionmaker

from project_g.infrastructure.collectors import (
    GiantsOfficialNewsCollector,
    GiantsOfficialNewsParser,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    create_database_engine,
)
from project_g.infrastructure.database.repositories import (
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
    """Process one queued news metadata enrichment job."""
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

    try:
        with factory.begin() as session:
            result = enrich_news_metadata(
                session=session,
                settings=settings,
                intake_id=parsed_intake_id,
            )
    finally:
        engine.dispose()

    return {
        "status": "processed",
        "intake_id": str(result.metadata.intake_id),
        "metadata_status": result.metadata.status.value,
        "processing_status": result.processing_job.status.value,
    }


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

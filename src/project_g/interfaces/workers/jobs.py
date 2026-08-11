from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import sessionmaker

from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    create_database_engine,
)
from project_g.interfaces.management.enrich_news_metadata import (
    enrich_news_metadata,
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
        "metadata_status": (result.metadata.status.value),
        "processing_status": (result.processing_job.status.value),
    }

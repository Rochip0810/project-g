import sys
from argparse import (
    ArgumentParser,
    ArgumentTypeError,
    Namespace,
)
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TextIO
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from project_g.application.news.complete_metadata_enrichment import (
    CompleteManualNewsMetadataEnrichment,
    NewsMetadataEnrichmentResult,
    NewsMetadataEnrichmentTargetNotFoundError,
)
from project_g.domain.news.article_metadata import (
    InvalidNewsArticleMetadataError,
    InvalidNewsMetadataTransitionError,
)
from project_g.domain.news.processing_job import (
    InvalidNewsProcessingTransitionError,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    create_database_engine,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyNewsArticleMetadataRepository,
    SqlAlchemyNewsProcessingJobRepository,
)


def parse_published_at(value: str) -> datetime:
    normalized = value.strip()

    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ArgumentTypeError("published-at must be an ISO 8601 datetime") from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ArgumentTypeError("published-at must include a timezone, for example +09:00")

    return parsed.astimezone(UTC)


def parse_arguments(
    argv: Sequence[str] | None = None,
) -> Namespace:
    parser = ArgumentParser(
        description=("Record manually confirmed article metadata for one submitted news URL.")
    )
    parser.add_argument(
        "intake_id",
        type=UUID,
        help="Manual news intake UUID.",
    )
    parser.add_argument(
        "--title",
        required=True,
        help="Confirmed article title.",
    )
    parser.add_argument(
        "--published-at",
        type=parse_published_at,
        default=None,
        help=("Optional ISO 8601 publication datetime. A timezone is required."),
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Optional article description.",
    )

    return parser.parse_args(argv)


def set_manual_metadata(
    *,
    session: Session,
    intake_id: UUID,
    title: str,
    published_at: datetime | None,
    description: str | None,
) -> NewsMetadataEnrichmentResult:
    metadata_repository = SqlAlchemyNewsArticleMetadataRepository(session)
    job_repository = SqlAlchemyNewsProcessingJobRepository(session)

    service = CompleteManualNewsMetadataEnrichment(
        metadata_repository=metadata_repository,
        job_repository=job_repository,
    )

    return service.execute(
        intake_id=intake_id,
        title=title,
        published_at=published_at,
        description=description,
    )


def print_result(
    result: NewsMetadataEnrichmentResult,
    *,
    output: TextIO,
) -> None:
    metadata = result.metadata
    job = result.processing_job

    print("status=updated", file=output)
    print(f"intake_id={metadata.intake_id}", file=output)
    print(
        f"article_metadata_id={metadata.metadata_id}",
        file=output,
    )
    print(
        f"article_metadata_status={metadata.status.value}",
        file=output,
    )
    print(f"title={metadata.title}", file=output)
    print(
        "published_at="
        + (metadata.published_at.isoformat() if metadata.published_at is not None else ""),
        file=output,
    )
    print(
        f"description={metadata.description or ''}",
        file=output,
    )
    print(f"processing_job_id={job.job_id}", file=output)
    print(
        f"processing_status={job.status.value}",
        file=output,
    )


def main(
    argv: Sequence[str] | None = None,
) -> None:
    arguments = parse_arguments(argv)
    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    try:
        with factory.begin() as session:
            result = set_manual_metadata(
                session=session,
                intake_id=arguments.intake_id,
                title=arguments.title,
                published_at=arguments.published_at,
                description=arguments.description,
            )
    except NewsMetadataEnrichmentTargetNotFoundError as error:
        print("status=not_found", file=sys.stderr)
        print(f"message={error}", file=sys.stderr)
        raise SystemExit(3) from error
    except (
        InvalidNewsArticleMetadataError,
        InvalidNewsMetadataTransitionError,
        InvalidNewsProcessingTransitionError,
    ) as error:
        print("status=rejected", file=sys.stderr)
        print(f"message={error}", file=sys.stderr)
        raise SystemExit(2) from error
    finally:
        engine.dispose()

    print_result(result, output=sys.stdout)


if __name__ == "__main__":
    main()

import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from typing import TextIO
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from project_g.application.news.auto_enrich_article_metadata import (
    AutoEnrichNewsArticleMetadata,
)
from project_g.application.news.complete_metadata_enrichment import (
    NewsMetadataEnrichmentResult,
    NewsMetadataEnrichmentTargetNotFoundError,
)
from project_g.domain.news.article_metadata import (
    InvalidNewsArticleMetadataError,
    InvalidNewsMetadataTransitionError,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.processing_job import (
    InvalidNewsProcessingTransitionError,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    create_database_engine,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsArticleMetadataRepository,
    SqlAlchemyNewsProcessingJobRepository,
)
from project_g.infrastructure.http import HttpxHttpClient
from project_g.infrastructure.news_metadata import (
    MAX_HTML_CHARACTERS,
    SafeHtmlNewsMetadataParser,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeRepository,
)

SOURCE_ALLOWED_HOSTS: dict[str, frozenset[str]] = {
    "giants_official_news": frozenset(
        {
            "www.giants.jp",
            "giants.jp",
        }
    ),
    "giants_official_schedule": frozenset(
        {
            "www.giants.jp",
            "giants.jp",
        }
    ),
    "npb_official_schedule": frozenset(
        {
            "npb.jp",
            "www.npb.jp",
        }
    ),
    "npb_official_stats": frozenset(
        {
            "npb.jp",
            "www.npb.jp",
        }
    ),
    "hochi_giants_x": frozenset(
        {
            "x.com",
            "www.x.com",
        }
    ),
    "hochi_giants_articles": frozenset(
        {
            "hochi.news",
            "www.hochi.news",
        }
    ),
    "hochi_giants_instagram": frozenset(
        {
            "instagram.com",
            "www.instagram.com",
        }
    ),
}


class NewsMetadataIntakeNotFoundError(RuntimeError):
    def __init__(self, intake_id: UUID) -> None:
        super().__init__(f"Manual news intake was not found: {intake_id}")
        self.intake_id = intake_id


class NewsMetadataSourceNotConfiguredError(RuntimeError):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"Automatic metadata access is not configured for source: {source_id}")
        self.source_id = source_id


def parse_arguments(
    argv: Sequence[str] | None = None,
) -> Namespace:
    parser = ArgumentParser(description=("Safely extract metadata for one registered news URL."))
    parser.add_argument(
        "intake_id",
        type=UUID,
        help="Manual news intake UUID.",
    )

    return parser.parse_args(argv)


def load_intake(
    *,
    repository: ManualNewsIntakeRepository,
    intake_id: UUID,
) -> ManualNewsIntake:
    intake = repository.get_by_intake_id(intake_id)

    if intake is None:
        raise NewsMetadataIntakeNotFoundError(intake_id)

    return intake


def get_allowed_hosts(
    source_id: str,
) -> frozenset[str]:
    allowed_hosts = SOURCE_ALLOWED_HOSTS.get(source_id)

    if allowed_hosts is None:
        raise NewsMetadataSourceNotConfiguredError(source_id)

    return allowed_hosts


def enrich_news_metadata(
    *,
    session: Session,
    settings: Settings,
    intake_id: UUID,
) -> NewsMetadataEnrichmentResult:
    intake_repository = SqlAlchemyManualNewsIntakeRepository(session)
    intake = load_intake(
        repository=intake_repository,
        intake_id=intake_id,
    )
    allowed_hosts = get_allowed_hosts(intake.source_id)

    metadata_repository = SqlAlchemyNewsArticleMetadataRepository(session)
    job_repository = SqlAlchemyNewsProcessingJobRepository(session)

    service = AutoEnrichNewsArticleMetadata(
        http_client=HttpxHttpClient(
            user_agent=settings.collection_user_agent,
            max_redirects=(settings.collection_max_redirects),
        ),
        parser=SafeHtmlNewsMetadataParser(),
        metadata_repository=metadata_repository,
        job_repository=job_repository,
        timeout_seconds=(settings.collection_request_timeout_seconds),
        max_response_bytes=min(
            settings.collection_max_response_bytes,
            MAX_HTML_CHARACTERS,
        ),
    )

    return service.execute(
        intake_id=intake.intake_id,
        url=intake.canonical_url,
        allowed_hosts=allowed_hosts,
    )


def print_result(
    result: NewsMetadataEnrichmentResult,
    *,
    output: TextIO,
) -> None:
    metadata = result.metadata
    job = result.processing_job

    print("status=processed", file=output)
    print(
        f"intake_id={metadata.intake_id}",
        file=output,
    )
    print(
        f"article_metadata_id={metadata.metadata_id}",
        file=output,
    )
    print(
        f"article_metadata_status={metadata.status.value}",
        file=output,
    )
    print(
        f"title={metadata.title or ''}",
        file=output,
    )
    print(
        "published_at="
        + (metadata.published_at.isoformat() if metadata.published_at is not None else ""),
        file=output,
    )
    print(
        f"description={metadata.description or ''}",
        file=output,
    )
    print(
        f"failure_reason={metadata.failure_reason or ''}",
        file=output,
    )
    print(
        f"processing_job_id={job.job_id}",
        file=output,
    )
    print(
        f"processing_status={job.status.value}",
        file=output,
    )
    print(
        f"processing_error={job.last_error or ''}",
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
            result = enrich_news_metadata(
                session=session,
                settings=settings,
                intake_id=arguments.intake_id,
            )
    except (
        NewsMetadataIntakeNotFoundError,
        NewsMetadataEnrichmentTargetNotFoundError,
    ) as error:
        print("status=not_found", file=sys.stderr)
        print(f"message={error}", file=sys.stderr)
        raise SystemExit(3) from error
    except (
        NewsMetadataSourceNotConfiguredError,
        InvalidNewsArticleMetadataError,
        InvalidNewsMetadataTransitionError,
        InvalidNewsProcessingTransitionError,
    ) as error:
        print("status=rejected", file=sys.stderr)
        print(f"message={error}", file=sys.stderr)
        raise SystemExit(2) from error
    finally:
        engine.dispose()

    print_result(
        result,
        output=sys.stdout,
    )


if __name__ == "__main__":
    main()

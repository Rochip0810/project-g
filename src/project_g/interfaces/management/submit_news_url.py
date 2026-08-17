import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TextIO

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session, sessionmaker

from project_g.application.news.create_article_metadata import (
    CreateNewsArticleMetadata,
)
from project_g.application.news.create_manual_intake import (
    CreateManualNewsIntake,
)
from project_g.application.news.create_processing_job import (
    CreateNewsProcessingJob,
)
from project_g.application.news.create_relevance_analysis import (
    CreateNewsRelevanceAnalysis,
)
from project_g.application.news.enqueue_metadata_processing import (
    EnqueueNewsMetadataProcessing,
)
from project_g.application.news.initial_sources import (
    INITIAL_NEWS_SOURCES,
)
from project_g.application.news.manual_url import (
    ManualNewsUrlError,
    ManualNewsUrlResolver,
)
from project_g.application.news.seed_sources import (
    seed_initial_news_sources,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.domain.news.processing_job import NewsProcessingJob
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import create_database_engine
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsArticleMetadataRepository,
    SqlAlchemyNewsProcessingJobRepository,
    SqlAlchemyNewsRelevanceAnalysisRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.infrastructure.queue import (
    create_redis_connection_pool,
)
from project_g.infrastructure.queue.rq_provider import (
    RQQueueProvider,
)
from project_g.ports.queue import (
    JobSnapshot,
    QueueProvider,
)
from project_g.ports.repositories import (
    ManualNewsIntakeAlreadyExistsError,
    NewsArticleMetadataAlreadyExistsError,
    NewsProcessingJobAlreadyExistsError,
    NewsRelevanceAnalysisAlreadyExistsError,
)


@dataclass(frozen=True, slots=True)
class SubmittedNewsUrl:
    intake: ManualNewsIntake
    processing_job: NewsProcessingJob
    article_metadata: NewsArticleMetadata
    relevance_analysis: NewsRelevanceAnalysis


def parse_arguments(
    argv: Sequence[str] | None = None,
) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Register one news URL and create its pending "
            "processing job, metadata, and relevance-analysis records without "
            "fetching article content."
        )
    )
    parser.add_argument(
        "url",
        help="HTTPS URL from a registered Project G news source.",
    )

    return parser.parse_args(argv)


def create_manual_intake(
    *,
    session: Session,
    submitted_url: str,
) -> ManualNewsIntake:
    source_repository = SqlAlchemyNewsSourceRepository(session)
    seed_initial_news_sources(source_repository)

    intake_repository = SqlAlchemyManualNewsIntakeRepository(session)
    service = CreateManualNewsIntake(
        resolver=ManualNewsUrlResolver(INITIAL_NEWS_SOURCES),
        repository=intake_repository,
    )

    return service.execute(submitted_url)


def create_manual_intake_and_job(
    *,
    session: Session,
    submitted_url: str,
) -> SubmittedNewsUrl:
    intake = create_manual_intake(
        session=session,
        submitted_url=submitted_url,
    )

    job_repository = SqlAlchemyNewsProcessingJobRepository(session)
    processing_job = CreateNewsProcessingJob(
        repository=job_repository,
    ).execute(intake.intake_id)

    metadata_repository = SqlAlchemyNewsArticleMetadataRepository(session)
    article_metadata = CreateNewsArticleMetadata(
        repository=metadata_repository,
    ).execute(intake.intake_id)

    relevance_repository = SqlAlchemyNewsRelevanceAnalysisRepository(session)
    relevance_analysis = CreateNewsRelevanceAnalysis(
        repository=relevance_repository,
    ).execute(intake.intake_id)

    return SubmittedNewsUrl(
        intake=intake,
        processing_job=processing_job,
        article_metadata=article_metadata,
        relevance_analysis=relevance_analysis,
    )


def enqueue_submission(
    *,
    queue_provider: QueueProvider,
    submission: SubmittedNewsUrl,
) -> JobSnapshot:
    return EnqueueNewsMetadataProcessing(
        queue_provider=queue_provider,
    ).execute(submission.processing_job)


def enqueue_submission_with_rq(
    *,
    settings: Settings,
    submission: SubmittedNewsUrl,
) -> JobSnapshot:
    connection_pool = create_redis_connection_pool(
        settings,
        decode_responses=False,
    )
    connection = Redis.from_pool(connection_pool)

    try:
        provider = RQQueueProvider(
            settings,
            connection,
        )

        return enqueue_submission(
            queue_provider=provider,
            submission=submission,
        )
    finally:
        connection.close()
        connection_pool.close()


def print_queue_result(
    snapshot: JobSnapshot,
    *,
    output: TextIO,
) -> None:
    print(
        f"queue_job_id={snapshot.job_id}",
        file=output,
    )
    print(
        f"queue_name={snapshot.queue.value}",
        file=output,
    )
    print(
        f"queue_status={snapshot.status}",
        file=output,
    )


def print_submission(
    submission: SubmittedNewsUrl,
    *,
    output: TextIO,
) -> None:
    intake = submission.intake
    job = submission.processing_job
    metadata = submission.article_metadata
    relevance = submission.relevance_analysis

    print("status=created", file=output)
    print(f"intake_id={intake.intake_id}", file=output)
    print(f"source_id={intake.source_id}", file=output)
    print(f"submitted_url={intake.submitted_url}", file=output)
    print(f"canonical_url={intake.canonical_url}", file=output)
    print(
        f"submitted_at={intake.submitted_at.isoformat()}",
        file=output,
    )
    print(f"processing_job_id={job.job_id}", file=output)
    print(
        f"processing_status={job.status.value}",
        file=output,
    )
    print(
        f"processing_attempt_count={job.attempt_count}",
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
        f"relevance_analysis_id={relevance.analysis_id}",
        file=output,
    )
    print(
        f"relevance_analysis_status={relevance.status.value}",
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
            submission = create_manual_intake_and_job(
                session=session,
                submitted_url=arguments.url,
            )
    except ManualNewsIntakeAlreadyExistsError as error:
        print("status=duplicate", file=sys.stderr)
        print(
            f"canonical_url={error.canonical_url}",
            file=sys.stderr,
        )
        raise SystemExit(3) from error
    except NewsProcessingJobAlreadyExistsError as error:
        print(
            "status=processing_job_duplicate",
            file=sys.stderr,
        )
        print(
            f"intake_id={error.intake_id}",
            file=sys.stderr,
        )
        raise SystemExit(4) from error
    except NewsArticleMetadataAlreadyExistsError as error:
        print(
            "status=article_metadata_duplicate",
            file=sys.stderr,
        )
        print(
            f"intake_id={error.intake_id}",
            file=sys.stderr,
        )
        raise SystemExit(5) from error
    except NewsRelevanceAnalysisAlreadyExistsError as error:
        print(
            "status=relevance_analysis_duplicate",
            file=sys.stderr,
        )
        print(
            f"intake_id={error.intake_id}",
            file=sys.stderr,
        )
        raise SystemExit(7) from error
    except ManualNewsUrlError as error:
        print("status=rejected", file=sys.stderr)
        print(f"message={error}", file=sys.stderr)
        raise SystemExit(2) from error
    finally:
        engine.dispose()

    try:
        queue_snapshot = enqueue_submission_with_rq(
            settings=settings,
            submission=submission,
        )
    except RedisError as error:
        print(
            "status=queue_failed",
            file=sys.stderr,
        )
        print(
            f"intake_id={submission.intake.intake_id}",
            file=sys.stderr,
        )
        print(
            "message=News URL was saved but queue submission failed",
            file=sys.stderr,
        )
        raise SystemExit(6) from error

    print_submission(
        submission,
        output=sys.stdout,
    )
    print_queue_result(
        queue_snapshot,
        output=sys.stdout,
    )


if __name__ == "__main__":
    main()

import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TextIO

from sqlalchemy.orm import Session, sessionmaker

from project_g.application.news.create_manual_intake import (
    CreateManualNewsIntake,
)
from project_g.application.news.create_processing_job import (
    CreateNewsProcessingJob,
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
from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.domain.news.processing_job import NewsProcessingJob
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import create_database_engine
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsProcessingJobRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories import (
    ManualNewsIntakeAlreadyExistsError,
    NewsProcessingJobAlreadyExistsError,
)


@dataclass(frozen=True, slots=True)
class SubmittedNewsUrl:
    intake: ManualNewsIntake
    processing_job: NewsProcessingJob


def parse_arguments(
    argv: Sequence[str] | None = None,
) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Register one news URL and create its pending "
            "processing job without fetching article content."
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

    return SubmittedNewsUrl(
        intake=intake,
        processing_job=processing_job,
    )


def print_submission(
    submission: SubmittedNewsUrl,
    *,
    output: TextIO,
) -> None:
    intake = submission.intake
    job = submission.processing_job

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
    except ManualNewsUrlError as error:
        print("status=rejected", file=sys.stderr)
        print(f"message={error}", file=sys.stderr)
        raise SystemExit(2) from error
    finally:
        engine.dispose()

    print_submission(
        submission,
        output=sys.stdout,
    )


if __name__ == "__main__":
    main()

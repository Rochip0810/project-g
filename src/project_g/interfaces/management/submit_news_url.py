import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from typing import TextIO

from sqlalchemy.orm import Session, sessionmaker

from project_g.application.news.create_manual_intake import (
    CreateManualNewsIntake,
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
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import create_database_engine
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.ports.repositories import (
    ManualNewsIntakeAlreadyExistsError,
)


def parse_arguments(
    argv: Sequence[str] | None = None,
) -> Namespace:
    parser = ArgumentParser(
        description=("Register one news URL without fetching its article content.")
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


def print_intake(
    intake: ManualNewsIntake,
    *,
    output: TextIO,
) -> None:
    print("status=created", file=output)
    print(f"intake_id={intake.intake_id}", file=output)
    print(f"source_id={intake.source_id}", file=output)
    print(f"submitted_url={intake.submitted_url}", file=output)
    print(f"canonical_url={intake.canonical_url}", file=output)
    print(
        f"submitted_at={intake.submitted_at.isoformat()}",
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
            intake = create_manual_intake(
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
    except ManualNewsUrlError as error:
        print("status=rejected", file=sys.stderr)
        print(f"message={error}", file=sys.stderr)
        raise SystemExit(2) from error
    finally:
        engine.dispose()

    print_intake(
        intake,
        output=sys.stdout,
    )


if __name__ == "__main__":
    main()

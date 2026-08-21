import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TextIO

from sqlalchemy.orm import sessionmaker

from project_g.application.news.rank_candidates import (
    RankNewsCandidates,
)
from project_g.domain.news.ranking import (
    RankedNewsCandidate,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    create_database_engine,
)
from project_g.infrastructure.database.repositories.news_ranking_candidates import (
    SqlAlchemyNewsRankingCandidateRepository,
)


def parse_arguments(
    argv: Sequence[str] | None = None,
) -> Namespace:
    parser = ArgumentParser(description=("Rank current Project G news candidates."))
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of ranked items to display.",
    )

    arguments = parser.parse_args(argv)

    if not 1 <= arguments.limit <= 50:
        parser.error("--limit must be between 1 and 50")

    return arguments


def print_rankings(
    rankings: list[RankedNewsCandidate],
    *,
    output: TextIO,
) -> None:
    print("status=ok", file=output)
    print(
        f"candidate_count={len(rankings)}",
        file=output,
    )

    for position, candidate in enumerate(
        rankings,
        start=1,
    ):
        published_at = (
            candidate.published_at.isoformat() if candidate.published_at is not None else "unknown"
        )

        print(
            f"\nrank={position}",
            file=output,
        )
        print(
            f"intake_id={candidate.intake_id}",
            file=output,
        )
        print(
            f"title={candidate.title}",
            file=output,
        )
        print(
            f"published_at={published_at}",
            file=output,
        )
        print(
            f"relevance_score={candidate.relevance_score}",
            file=output,
        )
        print(
            f"priority_score={candidate.priority_score}",
            file=output,
        )
        print(
            f"freshness_score={candidate.freshness_score}",
            file=output,
        )
        print(
            f"ranking_score={candidate.ranking_score}",
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
        with factory() as session:
            repository = SqlAlchemyNewsRankingCandidateRepository(session)
            service = RankNewsCandidates(repository)

            rankings = service.execute(
                now=datetime.now(UTC),
                limit=arguments.limit,
            )

            print_rankings(
                rankings,
                output=sys.stdout,
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

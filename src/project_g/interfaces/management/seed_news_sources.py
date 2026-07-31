from sqlalchemy.orm import sessionmaker

from project_g.application.news import (
    seed_initial_news_sources,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    create_database_engine,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyNewsSourceRepository,
)


def main() -> None:
    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    try:
        with factory.begin() as session:
            repository = SqlAlchemyNewsSourceRepository(session)
            result = seed_initial_news_sources(repository)
    finally:
        engine.dispose()

    print("Initial news-source seeding completed")
    print(f"added={result.added_count}")
    print(f"existing={result.existing_count}")
    print(f"total={result.total_count}")


if __name__ == "__main__":
    main()

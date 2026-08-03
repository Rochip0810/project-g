from project_g.infrastructure.database.repositories.manual_news_intakes import (
    SqlAlchemyManualNewsIntakeRepository,
)
from project_g.infrastructure.database.repositories.news_sources import (
    SqlAlchemyNewsSourceRepository,
)

__all__ = [
    "SqlAlchemyManualNewsIntakeRepository",
    "SqlAlchemyNewsSourceRepository",
]

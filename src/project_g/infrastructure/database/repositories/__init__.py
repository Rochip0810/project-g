from project_g.infrastructure.database.repositories.manual_news_intakes import (
    SqlAlchemyManualNewsIntakeRepository,
)
from project_g.infrastructure.database.repositories.news_article_metadata import (
    SqlAlchemyNewsArticleMetadataRepository,
)
from project_g.infrastructure.database.repositories.news_priority_analyses import (
    SqlAlchemyNewsPriorityAnalysisRepository,
)
from project_g.infrastructure.database.repositories.news_processing_jobs import (
    SqlAlchemyNewsProcessingJobRepository,
)
from project_g.infrastructure.database.repositories.news_relevance_analyses import (
    SqlAlchemyNewsRelevanceAnalysisRepository,
)
from project_g.infrastructure.database.repositories.news_script_generations import (
    SqlAlchemyNewsScriptGenerationRepository,
)
from project_g.infrastructure.database.repositories.news_sources import (
    SqlAlchemyNewsSourceRepository,
)
from project_g.infrastructure.database.repositories.recent_news_context import (
    SqlAlchemyRecentNewsContextRepository,
)

__all__ = [
    "SqlAlchemyManualNewsIntakeRepository",
    "SqlAlchemyNewsArticleMetadataRepository",
    "SqlAlchemyNewsPriorityAnalysisRepository",
    "SqlAlchemyNewsProcessingJobRepository",
    "SqlAlchemyNewsRelevanceAnalysisRepository",
    "SqlAlchemyNewsScriptGenerationRepository",
    "SqlAlchemyNewsSourceRepository",
    "SqlAlchemyRecentNewsContextRepository",
]

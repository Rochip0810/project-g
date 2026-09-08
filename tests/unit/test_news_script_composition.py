from pydantic import SecretStr
from sqlalchemy.orm import Session

from project_g.application.news.generate_news_script import (
    GenerateNewsScript,
)
from project_g.infrastructure.composition.news_script import (
    build_generate_news_script,
)
from project_g.infrastructure.config import Settings


def test_builds_real_news_script_service_without_network_calls() -> None:
    settings = Settings(
        openai_api_key=SecretStr("test-key"),
    )

    def session_factory() -> Session:
        return Session()

    service = build_generate_news_script(
        session_factory=session_factory,
        settings=settings,
    )

    assert isinstance(
        service,
        GenerateNewsScript,
    )

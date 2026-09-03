from sqlalchemy.orm import Session

from project_g.application.news.build_script_background_facts import (
    BuildNewsScriptBackgroundFacts,
)
from project_g.application.news.collect_npb_authoritative_facts import (
    CollectNPBAuthoritativeFacts,
)
from project_g.application.news.generate_news_script import (
    GenerateNewsScript,
)
from project_g.infrastructure.ai.openai_context import (
    OpenAINewsContextSelector,
)
from project_g.infrastructure.ai.openai_npb_player import (
    OpenAINPBPitchingPlayerSelector,
)
from project_g.infrastructure.ai.openai_script import (
    OpenAINewsScriptGenerator,
)
from project_g.infrastructure.background.npb_discovery import (
    NPBOfficialPitchingEvidenceDiscovery,
)
from project_g.infrastructure.background.npb_game import (
    NPBGameEvidenceExtractor,
)
from project_g.infrastructure.background.npb_schedule import (
    NPBGiantsGameUrlDiscovery,
    NPBGiantsScheduleParser,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database.repositories.recent_news_context import (
    SqlAlchemyRecentNewsContextRepository,
)
from project_g.infrastructure.http import HttpxHttpClient


def build_generate_news_script(
    *,
    session: Session,
    settings: Settings,
) -> GenerateNewsScript:
    api_key = settings.openai_api_key.get_secret_value()

    http_client = HttpxHttpClient(
        user_agent=settings.collection_user_agent,
        max_redirects=settings.collection_max_redirects,
    )

    context_selector = OpenAINewsContextSelector(
        api_key=api_key,
        model=settings.openai_context_model,
        timeout_seconds=(settings.openai_request_timeout_seconds),
    )

    background_builder = BuildNewsScriptBackgroundFacts(
        repository=(SqlAlchemyRecentNewsContextRepository(session)),
        selector=context_selector,
    )

    player_selector = OpenAINPBPitchingPlayerSelector(
        api_key=api_key,
        model=settings.openai_npb_player_model,
        timeout_seconds=(settings.openai_request_timeout_seconds),
    )

    game_url_discovery = NPBGiantsGameUrlDiscovery(
        http_client=http_client,
        parser=NPBGiantsScheduleParser(),
        timeout_seconds=(settings.collection_request_timeout_seconds),
        max_response_bytes=(settings.collection_max_response_bytes),
    )

    evidence_discovery = NPBOfficialPitchingEvidenceDiscovery(
        player_selector=player_selector,
        game_url_discovery=game_url_discovery,
        lookback_days=14,
    )

    authoritative_facts_provider = CollectNPBAuthoritativeFacts(
        discovery=evidence_discovery,
        http_client=http_client,
        extractor=NPBGameEvidenceExtractor(),
        timeout_seconds=(settings.collection_request_timeout_seconds),
        max_response_bytes=(settings.collection_max_response_bytes),
    )

    generator = OpenAINewsScriptGenerator(
        api_key=api_key,
        model=settings.openai_script_model,
        timeout_seconds=(settings.openai_request_timeout_seconds),
    )

    return GenerateNewsScript(
        background_builder=background_builder,
        authoritative_facts_provider=(authoritative_facts_provider),
        generator=generator,
    )

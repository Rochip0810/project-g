from datetime import UTC, datetime
from uuid import UUID

from redis import Redis
from rq import Retry
from rq.exceptions import DuplicateJobError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from project_g.application.news.analyze_priority import AnalyzeNewsPriority
from project_g.application.news.analyze_relevance import AnalyzeNewsRelevance
from project_g.application.news.create_priority_analysis import CreateNewsPriorityAnalysis
from project_g.application.news.enqueue_news_script_generation import (
    EnqueueNewsScriptGeneration,
)
from project_g.application.news.enqueue_priority_analysis import EnqueueNewsPriorityAnalysis
from project_g.application.news.enqueue_relevance_analysis import EnqueueNewsRelevanceAnalysis
from project_g.application.news.generate_news_script import GenerateNewsScriptInput
from project_g.application.news.manage_news_script_generation import (
    ManageNewsScriptGeneration,
)
from project_g.application.news.rank_candidates import RankNewsCandidates
from project_g.application.news.select_news_script_enqueue_candidates import (
    SelectNewsScriptEnqueueCandidates,
)
from project_g.domain.news.article_metadata import NewsMetadataStatus
from project_g.domain.news.priority_analysis import NewsPriorityStatus
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
    NewsRelevanceStatus,
)
from project_g.domain.news.script_generation import (
    NewsScriptGenerationStatus,
)
from project_g.infrastructure.ai.openai_priority import OpenAIPriorityAnalyzer
from project_g.infrastructure.ai.openai_relevance import OpenAIRelevanceAnalyzer
from project_g.infrastructure.collectors import (
    GiantsOfficialNewsCollector,
    GiantsOfficialNewsParser,
    HochiGiantsArticlesCollector,
    HochiGiantsArticlesParser,
)
from project_g.infrastructure.composition.news_script import (
    build_generate_news_script,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    create_database_engine,
)
from project_g.infrastructure.database.models import (
    NewsArticleMetadataRecord,
    NewsPriorityAnalysisRecord,
    NewsRelevanceAnalysisRecord,
)
from project_g.infrastructure.database.repositories import (
    SqlAlchemyManualNewsIntakeRepository,
    SqlAlchemyNewsArticleMetadataRepository,
    SqlAlchemyNewsPriorityAnalysisRepository,
    SqlAlchemyNewsRelevanceAnalysisRepository,
    SqlAlchemyNewsScriptGenerationRepository,
    SqlAlchemyNewsSourceRepository,
)
from project_g.infrastructure.database.repositories.news_ranking_candidates import (
    SqlAlchemyNewsRankingCandidateRepository,
)
from project_g.infrastructure.http import HttpxHttpClient
from project_g.infrastructure.queue import (
    RQQueueProvider,
    create_redis_connection_pool,
)
from project_g.interfaces.management.enrich_news_metadata import (
    enrich_news_metadata,
)
from project_g.workflows.news_discovery import (
    NewsDiscoveryWorkflow,
    SqlAlchemyCollectionRegistrationRunner,
)


def system_heartbeat(
    source: str = "worker",
) -> dict[str, str]:
    return {
        "status": "ok",
        "source": source,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def process_news_metadata(
    intake_id: str,
) -> dict[str, str]:
    """Process metadata and enqueue relevance analysis after commit."""
    try:
        parsed_intake_id = UUID(intake_id)
    except ValueError as error:
        raise ValueError(f"Invalid news intake UUID: {intake_id}") from error

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    relevance_analysis = None

    try:
        with factory.begin() as session:
            result = enrich_news_metadata(
                session=session,
                settings=settings,
                intake_id=parsed_intake_id,
            )

            if result.metadata.status is NewsMetadataStatus.EXTRACTED:
                relevance_repository = SqlAlchemyNewsRelevanceAnalysisRepository(session)
                relevance_analysis = relevance_repository.get_by_intake_id(parsed_intake_id)

                if relevance_analysis is None:
                    raise RuntimeError(
                        f"Relevance analysis was not found for intake: {parsed_intake_id}"
                    )

        relevance_queue_status = "skipped"
        relevance_job_id = ""

        if (
            relevance_analysis is not None
            and relevance_analysis.status is NewsRelevanceStatus.PENDING
        ):
            connection_pool = create_redis_connection_pool(
                settings,
                decode_responses=False,
            )
            connection = Redis.from_pool(connection_pool)

            try:
                queue_provider = RQQueueProvider(
                    settings,
                    connection,
                )

                snapshot = EnqueueNewsRelevanceAnalysis(queue_provider=queue_provider).execute(
                    relevance_analysis
                )

                relevance_queue_status = snapshot.status
                relevance_job_id = snapshot.job_id
            finally:
                connection.close()
                connection_pool.close()
        elif relevance_analysis is not None:
            relevance_queue_status = "already_processed"

        return {
            "status": "processed",
            "intake_id": str(result.metadata.intake_id),
            "metadata_status": result.metadata.status.value,
            "processing_status": (result.processing_job.status.value),
            "relevance_queue_status": (relevance_queue_status),
            "relevance_job_id": relevance_job_id,
        }

    finally:
        engine.dispose()


def process_news_relevance(
    intake_id: str,
) -> dict[str, str | int]:
    """Analyze relevance and hand eligible news to priority analysis."""
    try:
        parsed_intake_id = UUID(intake_id)
    except ValueError as error:
        raise ValueError(f"Invalid news intake UUID: {intake_id}") from error

    settings = Settings()

    analyzer = OpenAIRelevanceAnalyzer(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_relevance_model,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )

    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    priority_analysis = None
    decision: NewsRelevanceDecision | None = None

    try:
        with factory.begin() as session:
            service = AnalyzeNewsRelevance(
                intake_repository=(SqlAlchemyManualNewsIntakeRepository(session)),
                metadata_repository=(SqlAlchemyNewsArticleMetadataRepository(session)),
                relevance_repository=(SqlAlchemyNewsRelevanceAnalysisRepository(session)),
                analyzer=analyzer,
            )

            result = service.execute(parsed_intake_id)
            decision = result.analysis.decision

            if decision is None:
                raise RuntimeError("Analyzed relevance result has no decision")

            if decision in (
                NewsRelevanceDecision.ACCEPTED,
                NewsRelevanceDecision.REVIEW,
            ):
                priority_repository = SqlAlchemyNewsPriorityAnalysisRepository(session)

                priority_analysis = priority_repository.get_by_intake_id(parsed_intake_id)

                if priority_analysis is None:
                    priority_analysis = CreateNewsPriorityAnalysis(
                        repository=priority_repository
                    ).execute(parsed_intake_id)
    finally:
        engine.dispose()

    if decision is None:
        raise RuntimeError("Analyzed relevance result has no decision")

    priority_queue_status = "skipped"
    priority_job_id = ""

    if priority_analysis is not None and priority_analysis.status is NewsPriorityStatus.PENDING:
        connection_pool = create_redis_connection_pool(
            settings,
            decode_responses=False,
        )
        connection = Redis.from_pool(connection_pool)

        try:
            queue_provider = RQQueueProvider(
                settings,
                connection,
            )

            try:
                snapshot = EnqueueNewsPriorityAnalysis(queue_provider=queue_provider).execute(
                    priority_analysis
                )
            except DuplicateJobError:
                priority_queue_status = "duplicate"
            else:
                priority_queue_status = snapshot.status
                priority_job_id = snapshot.job_id
        finally:
            connection.close()
            connection_pool.close()

    elif priority_analysis is not None:
        priority_queue_status = "already_processed"

    return {
        "status": "processed",
        "intake_id": str(result.analysis.intake_id),
        "relevance_status": result.analysis.status.value,
        "relevance_score": result.analyzer_result.relevance_score,
        "decision": decision.value,
        "priority_queue_status": priority_queue_status,
        "priority_job_id": priority_job_id,
    }


def process_news_priority(
    intake_id: str,
) -> dict[str, str | int]:
    """Analyze one queued news item for editorial priority."""
    try:
        parsed_intake_id = UUID(intake_id)
    except ValueError as error:
        raise ValueError(f"Invalid news intake UUID: {intake_id}") from error

    settings = Settings()

    analyzer = OpenAIPriorityAnalyzer(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_priority_model,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )

    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    try:
        with factory.begin() as session:
            service = AnalyzeNewsPriority(
                intake_repository=(SqlAlchemyManualNewsIntakeRepository(session)),
                metadata_repository=(SqlAlchemyNewsArticleMetadataRepository(session)),
                relevance_repository=(SqlAlchemyNewsRelevanceAnalysisRepository(session)),
                priority_repository=(SqlAlchemyNewsPriorityAnalysisRepository(session)),
                analyzer=analyzer,
            )

            result = service.execute(parsed_intake_id)
    finally:
        engine.dispose()

    return {
        "status": "processed",
        "intake_id": str(result.analysis.intake_id),
        "priority_status": result.analysis.status.value,
        "priority_score": result.analyzer_result.priority_score,
    }


def recover_pending_news_relevance(
    limit: int = 20,
) -> dict[str, str | int]:
    """Re-enqueue ready relevance analyses left pending."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    try:
        with factory() as session:
            statement = (
                select(NewsRelevanceAnalysisRecord)
                .join(
                    NewsArticleMetadataRecord,
                    NewsArticleMetadataRecord.intake_id == NewsRelevanceAnalysisRecord.intake_id,
                )
                .where(
                    NewsRelevanceAnalysisRecord.status == NewsRelevanceStatus.PENDING.value,
                    NewsArticleMetadataRecord.status.in_(
                        [
                            NewsMetadataStatus.EXTRACTED.value,
                            NewsMetadataStatus.MANUAL.value,
                        ]
                    ),
                )
                .order_by(
                    NewsRelevanceAnalysisRecord.updated_at.asc(),
                    NewsRelevanceAnalysisRecord.analysis_id.asc(),
                )
                .limit(limit)
            )

            records = session.scalars(statement).all()

            analyses = [record.to_domain() for record in records]

        connection_pool = create_redis_connection_pool(
            settings,
            decode_responses=False,
        )
        connection = Redis.from_pool(connection_pool)

        enqueued_count = 0
        duplicate_count = 0

        try:
            queue_provider = RQQueueProvider(
                settings,
                connection,
            )
            service = EnqueueNewsRelevanceAnalysis(queue_provider=queue_provider)

            for analysis in analyses:
                try:
                    service.execute(analysis)
                except DuplicateJobError:
                    duplicate_count += 1
                else:
                    enqueued_count += 1
        finally:
            connection.close()
            connection_pool.close()

        return {
            "status": "processed",
            "scanned_count": len(analyses),
            "enqueued_count": enqueued_count,
            "duplicate_count": duplicate_count,
        }

    finally:
        engine.dispose()


def recover_pending_news_priority(
    limit: int = 20,
) -> dict[str, str | int]:
    """Re-enqueue ready editorial priority analyses left pending."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    try:
        with factory() as session:
            statement = (
                select(NewsPriorityAnalysisRecord)
                .join(
                    NewsArticleMetadataRecord,
                    NewsArticleMetadataRecord.intake_id == NewsPriorityAnalysisRecord.intake_id,
                )
                .join(
                    NewsRelevanceAnalysisRecord,
                    NewsRelevanceAnalysisRecord.intake_id == NewsPriorityAnalysisRecord.intake_id,
                )
                .where(
                    NewsPriorityAnalysisRecord.status == NewsPriorityStatus.PENDING.value,
                    NewsArticleMetadataRecord.status.in_(
                        [
                            NewsMetadataStatus.EXTRACTED.value,
                            NewsMetadataStatus.MANUAL.value,
                        ]
                    ),
                    NewsArticleMetadataRecord.title.is_not(None),
                    NewsRelevanceAnalysisRecord.status == NewsRelevanceStatus.ANALYZED.value,
                    NewsRelevanceAnalysisRecord.decision.in_(
                        [
                            NewsRelevanceDecision.ACCEPTED.value,
                            NewsRelevanceDecision.REVIEW.value,
                        ]
                    ),
                )
                .order_by(
                    NewsPriorityAnalysisRecord.updated_at.asc(),
                    NewsPriorityAnalysisRecord.analysis_id.asc(),
                )
                .limit(limit)
            )

            records = session.scalars(statement).all()

            analyses = [record.to_domain() for record in records]

        connection_pool = create_redis_connection_pool(
            settings,
            decode_responses=False,
        )
        connection = Redis.from_pool(connection_pool)

        enqueued_count = 0
        duplicate_count = 0

        try:
            queue_provider = RQQueueProvider(
                settings,
                connection,
            )

            service = EnqueueNewsPriorityAnalysis(queue_provider=queue_provider)

            for analysis in analyses:
                try:
                    service.execute(analysis)
                except DuplicateJobError:
                    duplicate_count += 1
                else:
                    enqueued_count += 1
        finally:
            connection.close()
            connection_pool.close()

        return {
            "status": "processed",
            "scanned_count": len(analyses),
            "enqueued_count": enqueued_count,
            "duplicate_count": duplicate_count,
        }

    finally:
        engine.dispose()


def discover_giants_news(
    max_items: int = 20,
) -> dict[str, str | int]:
    """Discover Giants news and enqueue new metadata jobs."""
    if not 1 <= max_items <= 50:
        raise ValueError("max_items must be between 1 and 50")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    connection_pool = create_redis_connection_pool(
        settings,
        decode_responses=False,
    )
    connection = Redis.from_pool(connection_pool)

    try:
        with factory() as session:
            source_repository = SqlAlchemyNewsSourceRepository(session)
            source = source_repository.get_by_source_id("giants_official_news")

        if source is None:
            return {
                "status": "source_missing",
                "source_id": "giants_official_news",
            }

        if not source.collectable:
            return {
                "status": "skipped",
                "source_id": source.source_id,
                "reason": "source_not_collectable",
            }

        collector = GiantsOfficialNewsCollector(
            source=source,
            http_client=HttpxHttpClient(
                user_agent=settings.collection_user_agent,
                max_redirects=settings.collection_max_redirects,
            ),
            parser=GiantsOfficialNewsParser(),
            max_response_bytes=(settings.collection_max_response_bytes),
        )

        queue_provider = RQQueueProvider(
            settings,
            connection,
        )

        workflow = NewsDiscoveryWorkflow(
            collector=collector,
            registration_runner=(
                SqlAlchemyCollectionRegistrationRunner(
                    session_factory=factory,
                )
            ),
            queue_provider=queue_provider,
        )

        result = workflow.execute(
            timeout_seconds=(settings.collection_request_timeout_seconds),
            max_items=max_items,
        )

        if result.registration is None:
            failure = result.collection.failure

            return {
                "status": "collection_failed",
                "source_id": source.source_id,
                "failure_code": (failure.code if failure is not None else "unknown"),
            }

        return {
            "status": "processed",
            "source_id": source.source_id,
            "discovered_count": (result.registration.discovered_count),
            "registered_count": (result.registration.registered_count),
            "duplicate_count": (result.registration.duplicate_count),
            "queued_count": result.queued_count,
        }
    finally:
        connection.close()
        connection_pool.close()
        engine.dispose()


def discover_hochi_giants_news(
    max_items: int = 5,
) -> dict[str, str | int]:
    """Discover Sports Hochi Giants articles and enqueue new metadata jobs."""
    if not 1 <= max_items <= 50:
        raise ValueError("max_items must be between 1 and 50")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    connection_pool = create_redis_connection_pool(
        settings,
        decode_responses=False,
    )
    connection = Redis.from_pool(connection_pool)

    try:
        with factory() as session:
            source_repository = SqlAlchemyNewsSourceRepository(session)
            source = source_repository.get_by_source_id("hochi_giants_articles")

        if source is None:
            return {
                "status": "source_missing",
                "source_id": "hochi_giants_articles",
            }

        if not source.collectable:
            return {
                "status": "skipped",
                "source_id": source.source_id,
                "reason": "source_not_collectable",
            }

        collector = HochiGiantsArticlesCollector(
            source=source,
            http_client=HttpxHttpClient(
                user_agent=settings.collection_user_agent,
                max_redirects=settings.collection_max_redirects,
            ),
            parser=HochiGiantsArticlesParser(),
            max_response_bytes=settings.collection_max_response_bytes,
        )

        queue_provider = RQQueueProvider(
            settings,
            connection,
        )

        workflow = NewsDiscoveryWorkflow(
            collector=collector,
            registration_runner=(
                SqlAlchemyCollectionRegistrationRunner(
                    session_factory=factory,
                )
            ),
            queue_provider=queue_provider,
        )

        result = workflow.execute(
            timeout_seconds=(settings.collection_request_timeout_seconds),
            max_items=max_items,
        )

        if result.registration is None:
            failure = result.collection.failure

            return {
                "status": "collection_failed",
                "source_id": source.source_id,
                "failure_code": (failure.code if failure is not None else "unknown"),
            }

        return {
            "status": "processed",
            "source_id": source.source_id,
            "discovered_count": (result.registration.discovered_count),
            "registered_count": (result.registration.registered_count),
            "duplicate_count": (result.registration.duplicate_count),
            "queued_count": result.queued_count,
        }
    finally:
        connection.close()
        connection_pool.close()
        engine.dispose()


def enqueue_ranked_news_scripts(
    limit: int = 5,
    min_ranking_score: int = 70,
) -> dict[str, str | int]:
    """Rank eligible news and enqueue script-generation jobs."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")

    if not 0 <= min_ranking_score <= 100:
        raise ValueError("min_ranking_score must be between 0 and 100")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    generation_version = 1
    enqueue_interval_seconds = 300

    try:
        # Read and select candidates inside a short-lived DB session.
        # Redis/RQ work starts only after this context is closed.
        with factory() as session:
            ranking_repository = SqlAlchemyNewsRankingCandidateRepository(session)
            generation_repository = SqlAlchemyNewsScriptGenerationRepository(session)

            rank_service = RankNewsCandidates(
                ranking_repository,
            )
            rankings = rank_service.execute_all(
                now=datetime.now(UTC),
            )

            selector = SelectNewsScriptEnqueueCandidates(
                repository=generation_repository,
            )
            candidates = selector.execute(
                rankings=rankings,
                generation_version=generation_version,
                min_ranking_score=min_ranking_score,
                limit=limit,
            )

        current_time = datetime.now(UTC)
        time_bucket = int(current_time.timestamp()) // enqueue_interval_seconds

        connection_pool = create_redis_connection_pool(
            settings,
            decode_responses=False,
        )
        connection = Redis.from_pool(connection_pool)

        enqueued_count = 0
        duplicate_count = 0

        try:
            queue_provider = RQQueueProvider(
                settings,
                connection,
            )
            enqueue_service = EnqueueNewsScriptGeneration(
                queue_provider=queue_provider,
            )

            for candidate in candidates:
                try:
                    enqueue_service.execute(
                        candidate,
                        time_bucket=time_bucket,
                    )
                except DuplicateJobError:
                    duplicate_count += 1
                else:
                    enqueued_count += 1
        finally:
            connection.close()
            connection_pool.close()

        return {
            "status": "processed",
            "ranked_count": len(rankings),
            "selected_count": len(candidates),
            "enqueued_count": enqueued_count,
            "duplicate_count": duplicate_count,
        }

    finally:
        engine.dispose()


def process_news_script(
    intake_id: str,
    ranking_score: int,
) -> dict[str, object] | Retry:
    """Generate and persist one grounded Project G news script."""
    try:
        parsed_intake_id = UUID(intake_id)
    except ValueError as error:
        raise ValueError(f"Invalid news intake UUID: {intake_id}") from error

    if not 0 <= ranking_score <= 100:
        raise ValueError("ranking_score must be between 0 and 100")

    settings = Settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    generation_version = 1

    try:
        claimed_generation = None
        existing_generation = None
        script_input: GenerateNewsScriptInput | None = None

        # Transaction 1:
        # Validate readiness, persist the durable generation record,
        # and atomically claim it before any network work starts.
        with factory.begin() as session:
            intake_repository = SqlAlchemyManualNewsIntakeRepository(session)
            metadata_repository = SqlAlchemyNewsArticleMetadataRepository(session)
            relevance_repository = SqlAlchemyNewsRelevanceAnalysisRepository(session)
            priority_repository = SqlAlchemyNewsPriorityAnalysisRepository(session)

            intake = intake_repository.get_by_intake_id(parsed_intake_id)
            if intake is None:
                raise RuntimeError(f"News intake was not found: {parsed_intake_id}")

            metadata = metadata_repository.get_by_intake_id(parsed_intake_id)
            if metadata is None:
                raise RuntimeError(f"News metadata was not found: {parsed_intake_id}")

            if metadata.status not in {
                NewsMetadataStatus.EXTRACTED,
                NewsMetadataStatus.MANUAL,
            }:
                raise RuntimeError("News metadata is not ready for script generation")

            title = metadata.title
            published_at = metadata.published_at

            if title is None:
                raise RuntimeError("News metadata has no title")

            if published_at is None:
                raise RuntimeError("News metadata has no published_at")

            relevance = relevance_repository.get_by_intake_id(parsed_intake_id)
            if relevance is None:
                raise RuntimeError(f"Relevance analysis was not found: {parsed_intake_id}")

            if relevance.status is not NewsRelevanceStatus.ANALYZED:
                raise RuntimeError("Relevance analysis is not ready")

            if relevance.decision not in {
                NewsRelevanceDecision.ACCEPTED,
                NewsRelevanceDecision.REVIEW,
            }:
                raise RuntimeError("News is not eligible for script generation")

            relevance_score = relevance.relevance_score
            if relevance_score is None:
                raise RuntimeError("Relevance analysis has no score")

            priority = priority_repository.get_by_intake_id(parsed_intake_id)
            if priority is None:
                raise RuntimeError(f"Priority analysis was not found: {parsed_intake_id}")

            if priority.status is not NewsPriorityStatus.ANALYZED:
                raise RuntimeError("Priority analysis is not ready")

            priority_score = priority.priority_score
            if priority_score is None:
                raise RuntimeError("Priority analysis has no score")

            generation_repository = SqlAlchemyNewsScriptGenerationRepository(session)
            manager = ManageNewsScriptGeneration(
                repository=generation_repository,
            )

            prepared_generation = manager.prepare(
                intake_id=parsed_intake_id,
                generation_version=generation_version,
                ranking_score=ranking_score,
            )

            if prepared_generation.status is NewsScriptGenerationStatus.GENERATED:
                existing_generation = prepared_generation
            else:
                claimed_generation = manager.claim(
                    intake_id=parsed_intake_id,
                    generation_version=generation_version,
                    stale_after_seconds=(settings.rq_job_timeout_seconds),
                )

                if claimed_generation is None:
                    existing_generation = generation_repository.get_by_intake_version(
                        intake_id=parsed_intake_id,
                        generation_version=(generation_version),
                    )

                    if existing_generation is None:
                        raise RuntimeError("Script generation state disappeared while claiming")
                else:
                    script_input = GenerateNewsScriptInput(
                        intake_id=parsed_intake_id,
                        source_id=intake.source_id,
                        title=title,
                        description=metadata.description,
                        canonical_url=intake.canonical_url,
                        published_at=published_at,
                        relevance_score=relevance_score,
                        priority_score=priority_score,
                        ranking_score=(claimed_generation.ranking_score),
                    )

        # The claim transaction has committed here.
        # No generation/OpenAI/NPB network call occurred
        # while that database transaction was open.
        if claimed_generation is None:
            assert existing_generation is not None

            if existing_generation.status is NewsScriptGenerationStatus.GENERATED:
                evidence_snapshot = existing_generation.evidence_snapshot or ()

                evidence = [
                    {
                        "text": fact.text,
                        "source_id": fact.source_id,
                        "source_url": fact.source_url,
                        "competition_level": (fact.competition_level.value),
                        "role": fact.role.value,
                    }
                    for fact in evidence_snapshot
                ]

                return {
                    "status": "already_generated",
                    "intake_id": str(parsed_intake_id),
                    "ranking_score": (existing_generation.ranking_score),
                    "hook": existing_generation.hook,
                    "main_narration": (existing_generation.main_narration),
                    "project_g_comment": (existing_generation.project_g_comment),
                    "closing": (existing_generation.closing),
                    "full_narration": (existing_generation.full_narration),
                    "evidence_count": len(evidence),
                    "evidence": evidence,
                }

            if existing_generation.status is NewsScriptGenerationStatus.GENERATING:
                return Retry(
                    max=1,
                    interval=settings.rq_job_timeout_seconds,
                )

            return {
                "status": (existing_generation.status.value),
                "intake_id": str(parsed_intake_id),
                "ranking_score": (existing_generation.ranking_score),
            }

        # Network-capable generation happens only after
        # the durable GENERATING claim has committed.
        assert script_input is not None

        service = build_generate_news_script(
            session_factory=factory,
            settings=settings,
        )

        try:
            result = service.execute(script_input)
        except Exception as error:
            failure_reason = f"{type(error).__name__}: news script generation failed"

            with factory.begin() as session:
                generation_repository = SqlAlchemyNewsScriptGenerationRepository(session)
                manager = ManageNewsScriptGeneration(
                    repository=generation_repository,
                )

                manager.mark_failed(
                    generation_id=(claimed_generation.generation_id),
                    reason=failure_reason,
                )

            raise

        # Transaction 2:
        # Persist the exact generated narration and
        # evidence snapshot after network work is complete.
        with factory.begin() as session:
            generation_repository = SqlAlchemyNewsScriptGenerationRepository(session)
            manager = ManageNewsScriptGeneration(
                repository=generation_repository,
            )

            generated = manager.record_generated(
                generation_id=(claimed_generation.generation_id),
                result=result,
            )

        evidence_snapshot = generated.evidence_snapshot or ()

        evidence = [
            {
                "text": fact.text,
                "source_id": fact.source_id,
                "source_url": fact.source_url,
                "competition_level": (fact.competition_level.value),
                "role": fact.role.value,
            }
            for fact in evidence_snapshot
        ]

        return {
            "status": "processed",
            "intake_id": str(parsed_intake_id),
            "ranking_score": generated.ranking_score,
            "hook": generated.hook,
            "main_narration": (generated.main_narration),
            "project_g_comment": (generated.project_g_comment),
            "closing": generated.closing,
            "full_narration": (generated.full_narration),
            "evidence_count": len(evidence),
            "evidence": evidence,
        }
    finally:
        engine.dispose()

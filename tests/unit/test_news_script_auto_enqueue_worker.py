from datetime import datetime
from types import TracebackType
from uuid import UUID

import pytest
from rq.exceptions import DuplicateJobError

from project_g.application.news.select_news_script_enqueue_candidates import (
    NewsScriptEnqueueCandidate,
)
from project_g.interfaces.workers.jobs import enqueue_ranked_news_scripts
from project_g.ports.queue import JobSnapshot, QueueName

_FIRST_ID = UUID("00000000-0000-0000-0000-000000000001")
_SECOND_ID = UUID("00000000-0000-0000-0000-000000000002")


def test_enqueue_ranked_news_scripts_closes_db_before_rq_and_counts_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from project_g.interfaces.workers import jobs

    events: list[str] = []

    class FakeSettings:
        pass

    class FakeEngine:
        def dispose(self) -> None:
            events.append("engine_dispose")

    class FakeSession:
        pass

    class FakeSessionContext:
        def __enter__(self) -> FakeSession:
            events.append("db_enter")
            return FakeSession()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            events.append("db_exit")

    class FakeSessionFactory:
        def __call__(self) -> FakeSessionContext:
            return FakeSessionContext()

    class FakeRankingRepository:
        def __init__(self, session: FakeSession) -> None:
            events.append("ranking_repository")

    class FakeGenerationRepository:
        def __init__(self, session: FakeSession) -> None:
            events.append("generation_repository")

    class FakeRankService:
        def __init__(self, repository: object) -> None:
            pass

        def execute_all(
            self,
            *,
            now: datetime,
        ) -> list[object]:
            assert now.tzinfo is not None
            events.append("rank")
            return ["ranked-1", "ranked-2"]

    class FakeSelector:
        def __init__(
            self,
            *,
            repository: object,
        ) -> None:
            pass

        def execute(
            self,
            *,
            rankings: list[object],
            generation_version: int,
            min_ranking_score: int,
            limit: int,
        ) -> list[NewsScriptEnqueueCandidate]:
            assert rankings == [
                "ranked-1",
                "ranked-2",
            ]
            assert generation_version == 1
            assert min_ranking_score == 70
            assert limit == 5

            events.append("select")

            return [
                NewsScriptEnqueueCandidate(
                    intake_id=_FIRST_ID,
                    generation_version=1,
                    ranking_score=88,
                ),
                NewsScriptEnqueueCandidate(
                    intake_id=_SECOND_ID,
                    generation_version=1,
                    ranking_score=91,
                ),
            ]

    class FakePool:
        def close(self) -> None:
            events.append("pool_close")

    class FakeConnection:
        def close(self) -> None:
            events.append("connection_close")

    class FakeRedis:
        @classmethod
        def from_pool(
            cls,
            pool: FakePool,
        ) -> FakeConnection:
            return FakeConnection()

    class FakeQueueProvider:
        def __init__(
            self,
            settings: object,
            connection: object,
        ) -> None:
            pass

    class FakeEnqueueService:
        def __init__(
            self,
            *,
            queue_provider: object,
        ) -> None:
            pass

        def execute(
            self,
            candidate: NewsScriptEnqueueCandidate,
            *,
            time_bucket: int,
        ) -> JobSnapshot:
            assert "db_exit" in events
            assert time_bucket >= 0

            events.append(f"enqueue:{candidate.intake_id}")

            if candidate.intake_id == _SECOND_ID:
                raise DuplicateJobError

            return JobSnapshot(
                job_id="job-1",
                queue=QueueName.DEFAULT,
                status="queued",
            )

    monkeypatch.setattr(
        jobs,
        "Settings",
        FakeSettings,
    )
    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda settings: FakeEngine(),
    )
    monkeypatch.setattr(
        jobs,
        "sessionmaker",
        lambda **kwargs: FakeSessionFactory(),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsRankingCandidateRepository",
        FakeRankingRepository,
        raising=False,
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsScriptGenerationRepository",
        FakeGenerationRepository,
    )
    monkeypatch.setattr(
        jobs,
        "RankNewsCandidates",
        FakeRankService,
        raising=False,
    )
    monkeypatch.setattr(
        jobs,
        "SelectNewsScriptEnqueueCandidates",
        FakeSelector,
        raising=False,
    )
    monkeypatch.setattr(
        jobs,
        "create_redis_connection_pool",
        lambda settings, decode_responses: FakePool(),
    )
    monkeypatch.setattr(
        jobs,
        "Redis",
        FakeRedis,
    )
    monkeypatch.setattr(
        jobs,
        "RQQueueProvider",
        FakeQueueProvider,
    )
    monkeypatch.setattr(
        jobs,
        "EnqueueNewsScriptGeneration",
        FakeEnqueueService,
        raising=False,
    )

    result = enqueue_ranked_news_scripts(
        limit=5,
        min_ranking_score=70,
    )

    assert result == {
        "status": "processed",
        "ranked_count": 2,
        "selected_count": 2,
        "enqueued_count": 1,
        "duplicate_count": 1,
    }

    assert events.index("db_exit") < events.index(f"enqueue:{_FIRST_ID}")
    assert events[-3:] == [
        "connection_close",
        "pool_close",
        "engine_dispose",
    ]


def test_enqueue_ranked_news_scripts_rejects_invalid_options() -> None:
    for limit, min_ranking_score in (
        (0, 70),
        (51, 70),
        (5, -1),
        (5, 101),
    ):
        try:
            enqueue_ranked_news_scripts(
                limit=limit,
                min_ranking_score=min_ranking_score,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Expected invalid enqueue options to fail")


def test_enqueue_ranked_news_scripts_does_not_cap_rankings_at_fifty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from project_g.interfaces.workers import jobs

    class FakeSettings:
        pass

    class FakeEngine:
        def dispose(self) -> None:
            pass

    class FakeSession:
        pass

    class FakeSessionContext:
        def __enter__(self) -> FakeSession:
            return FakeSession()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            pass

    class FakeSessionFactory:
        def __call__(self) -> FakeSessionContext:
            return FakeSessionContext()

    class FakeRankingRepository:
        def __init__(self, session: FakeSession) -> None:
            pass

    class FakeGenerationRepository:
        def __init__(self, session: FakeSession) -> None:
            pass

    class FakeRankService:
        def __init__(self, repository: object) -> None:
            pass

        def execute(
            self,
            *,
            now: datetime,
            limit: int,
        ) -> list[object]:
            raise AssertionError("worker must not cap rankings before generation-state filtering")

        def execute_all(
            self,
            *,
            now: datetime,
        ) -> list[object]:
            assert now.tzinfo is not None
            return [f"ranked-{index}" for index in range(51)]

    class FakeSelector:
        def __init__(
            self,
            *,
            repository: object,
        ) -> None:
            pass

        def execute(
            self,
            *,
            rankings: list[object],
            generation_version: int,
            min_ranking_score: int,
            limit: int,
        ) -> list[NewsScriptEnqueueCandidate]:
            assert len(rankings) == 51
            return []

    class FakePool:
        def close(self) -> None:
            pass

    class FakeConnection:
        def close(self) -> None:
            pass

    class FakeRedis:
        @classmethod
        def from_pool(
            cls,
            pool: FakePool,
        ) -> FakeConnection:
            return FakeConnection()

    class FakeQueueProvider:
        def __init__(
            self,
            settings: object,
            connection: object,
        ) -> None:
            pass

    monkeypatch.setattr(jobs, "Settings", FakeSettings)
    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda settings: FakeEngine(),
    )
    monkeypatch.setattr(
        jobs,
        "sessionmaker",
        lambda **kwargs: FakeSessionFactory(),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsRankingCandidateRepository",
        FakeRankingRepository,
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsScriptGenerationRepository",
        FakeGenerationRepository,
    )
    monkeypatch.setattr(
        jobs,
        "RankNewsCandidates",
        FakeRankService,
    )
    monkeypatch.setattr(
        jobs,
        "SelectNewsScriptEnqueueCandidates",
        FakeSelector,
    )
    monkeypatch.setattr(
        jobs,
        "create_redis_connection_pool",
        lambda settings, decode_responses: FakePool(),
    )
    monkeypatch.setattr(jobs, "Redis", FakeRedis)
    monkeypatch.setattr(
        jobs,
        "RQQueueProvider",
        FakeQueueProvider,
    )

    result = enqueue_ranked_news_scripts()

    assert result["ranked_count"] == 51
    assert result["selected_count"] == 0


def test_enqueue_ranked_news_scripts_cleans_up_when_queue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from project_g.interfaces.workers import jobs

    events: list[str] = []

    class FakeSettings:
        pass

    class FakeEngine:
        def dispose(self) -> None:
            events.append("engine_dispose")

    class FakeSession:
        pass

    class FakeSessionContext:
        def __enter__(self) -> FakeSession:
            events.append("db_enter")
            return FakeSession()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            events.append("db_exit")

    class FakeSessionFactory:
        def __call__(self) -> FakeSessionContext:
            return FakeSessionContext()

    class FakeRankingRepository:
        def __init__(self, session: FakeSession) -> None:
            pass

    class FakeGenerationRepository:
        def __init__(self, session: FakeSession) -> None:
            pass

    class FakeRankService:
        def __init__(self, repository: object) -> None:
            pass

        def execute_all(
            self,
            *,
            now: datetime,
        ) -> list[object]:
            return ["ranked"]

    class FakeSelector:
        def __init__(
            self,
            *,
            repository: object,
        ) -> None:
            pass

        def execute(
            self,
            *,
            rankings: list[object],
            generation_version: int,
            min_ranking_score: int,
            limit: int,
        ) -> list[NewsScriptEnqueueCandidate]:
            return [
                NewsScriptEnqueueCandidate(
                    intake_id=_FIRST_ID,
                    generation_version=1,
                    ranking_score=88,
                )
            ]

    class FakePool:
        def close(self) -> None:
            events.append("pool_close")

    class FakeConnection:
        def close(self) -> None:
            events.append("connection_close")

    class FakeRedis:
        @classmethod
        def from_pool(
            cls,
            pool: FakePool,
        ) -> FakeConnection:
            return FakeConnection()

    class FakeQueueProvider:
        def __init__(
            self,
            settings: object,
            connection: object,
        ) -> None:
            pass

    class FakeEnqueueService:
        def __init__(
            self,
            *,
            queue_provider: object,
        ) -> None:
            pass

        def execute(
            self,
            candidate: NewsScriptEnqueueCandidate,
            *,
            time_bucket: int,
        ) -> JobSnapshot:
            assert "db_exit" in events
            events.append("enqueue_failed")
            raise RuntimeError("queue unavailable")

    monkeypatch.setattr(jobs, "Settings", FakeSettings)
    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda settings: FakeEngine(),
    )
    monkeypatch.setattr(
        jobs,
        "sessionmaker",
        lambda **kwargs: FakeSessionFactory(),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsRankingCandidateRepository",
        FakeRankingRepository,
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsScriptGenerationRepository",
        FakeGenerationRepository,
    )
    monkeypatch.setattr(
        jobs,
        "RankNewsCandidates",
        FakeRankService,
    )
    monkeypatch.setattr(
        jobs,
        "SelectNewsScriptEnqueueCandidates",
        FakeSelector,
    )
    monkeypatch.setattr(
        jobs,
        "create_redis_connection_pool",
        lambda settings, decode_responses: FakePool(),
    )
    monkeypatch.setattr(jobs, "Redis", FakeRedis)
    monkeypatch.setattr(
        jobs,
        "RQQueueProvider",
        FakeQueueProvider,
    )
    monkeypatch.setattr(
        jobs,
        "EnqueueNewsScriptGeneration",
        FakeEnqueueService,
    )

    with pytest.raises(
        RuntimeError,
        match="queue unavailable",
    ):
        enqueue_ranked_news_scripts()

    assert events.index("db_exit") < events.index("enqueue_failed")
    assert events[-3:] == [
        "connection_close",
        "pool_close",
        "engine_dispose",
    ]

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

import project_g.interfaces.workers.jobs as module
from project_g.domain.news.priority_analysis import (
    NewsPriorityStatus,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
    NewsRelevanceStatus,
)
from project_g.ports.queue import (
    JobSnapshot,
    QueueName,
)

_INTAKE_ID = UUID("47b2c754-caf4-4c95-8b13-724af05d0757")
_PRIORITY_ANALYSIS_ID = UUID("57b2c754-caf4-4c95-8b13-724af05d0757")


class FakeSecret:
    def get_secret_value(self) -> str:
        return "test-key"


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeConnection:
    def close(self) -> None:
        pass


class FakePool:
    def close(self) -> None:
        pass


class FakeRedis:
    @staticmethod
    def from_pool(
        pool: Any,
    ) -> FakeConnection:
        return FakeConnection()


def _install_common_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    decision: NewsRelevanceDecision,
) -> dict[str, Any]:
    tracker: dict[str, Any] = {
        "priority_created": False,
        "priority_enqueued": False,
    }

    settings = SimpleNamespace(
        openai_api_key=FakeSecret(),
        openai_relevance_model="test-model",
        openai_request_timeout_seconds=30,
    )

    monkeypatch.setattr(
        module,
        "Settings",
        lambda: settings,
    )

    monkeypatch.setattr(
        module,
        "OpenAIRelevanceAnalyzer",
        lambda **kwargs: object(),
    )

    engine = FakeEngine()

    monkeypatch.setattr(
        module,
        "create_database_engine",
        lambda settings: engine,
    )

    class FakeFactory:
        def begin(
            self,
        ) -> Any:
            return nullcontext(object())

    monkeypatch.setattr(
        module,
        "sessionmaker",
        lambda **kwargs: FakeFactory(),
    )

    monkeypatch.setattr(
        module,
        "SqlAlchemyManualNewsIntakeRepository",
        lambda session: object(),
    )
    monkeypatch.setattr(
        module,
        "SqlAlchemyNewsArticleMetadataRepository",
        lambda session: object(),
    )
    monkeypatch.setattr(
        module,
        "SqlAlchemyNewsRelevanceAnalysisRepository",
        lambda session: object(),
    )

    class FakePriorityRepository:
        def get_by_intake_id(
            self,
            intake_id: UUID,
        ) -> None:
            return None

    monkeypatch.setattr(
        module,
        "SqlAlchemyNewsPriorityAnalysisRepository",
        lambda session: FakePriorityRepository(),
    )

    relevance_analysis = SimpleNamespace(
        intake_id=_INTAKE_ID,
        status=NewsRelevanceStatus.ANALYZED,
        decision=decision,
    )

    relevance_result = SimpleNamespace(
        analysis=relevance_analysis,
        analyzer_result=SimpleNamespace(
            relevance_score=95,
        ),
    )

    class FakeAnalyzeNewsRelevance:
        def __init__(
            self,
            **kwargs: Any,
        ) -> None:
            pass

        def execute(
            self,
            intake_id: UUID,
        ) -> Any:
            assert intake_id == _INTAKE_ID
            return relevance_result

    monkeypatch.setattr(
        module,
        "AnalyzeNewsRelevance",
        FakeAnalyzeNewsRelevance,
    )

    priority_analysis = SimpleNamespace(
        analysis_id=_PRIORITY_ANALYSIS_ID,
        intake_id=_INTAKE_ID,
        status=NewsPriorityStatus.PENDING,
        created_at=datetime(
            2026,
            8,
            21,
            10,
            0,
            tzinfo=UTC,
        ),
    )

    class FakeCreateNewsPriorityAnalysis:
        def __init__(
            self,
            *,
            repository: Any,
        ) -> None:
            pass

        def execute(
            self,
            intake_id: UUID,
        ) -> Any:
            tracker["priority_created"] = True
            assert intake_id == _INTAKE_ID
            return priority_analysis

    monkeypatch.setattr(
        module,
        "CreateNewsPriorityAnalysis",
        FakeCreateNewsPriorityAnalysis,
    )

    monkeypatch.setattr(
        module,
        "create_redis_connection_pool",
        lambda settings, decode_responses=False: FakePool(),
    )
    monkeypatch.setattr(
        module,
        "Redis",
        FakeRedis,
    )

    monkeypatch.setattr(
        module,
        "RQQueueProvider",
        lambda settings, connection: object(),
    )

    class FakeEnqueueNewsPriorityAnalysis:
        def __init__(
            self,
            *,
            queue_provider: Any,
        ) -> None:
            pass

        def execute(
            self,
            analysis: Any,
        ) -> JobSnapshot:
            tracker["priority_enqueued"] = True
            assert analysis is priority_analysis

            return JobSnapshot(
                job_id=(f"news-priority-{_PRIORITY_ANALYSIS_ID}"),
                queue=QueueName.DEFAULT,
                status="queued",
            )

    monkeypatch.setattr(
        module,
        "EnqueueNewsPriorityAnalysis",
        FakeEnqueueNewsPriorityAnalysis,
    )

    return tracker


@pytest.mark.parametrize(
    "decision",
    [
        NewsRelevanceDecision.ACCEPTED,
        NewsRelevanceDecision.REVIEW,
    ],
)
def test_eligible_relevance_creates_and_enqueues_priority(
    monkeypatch: pytest.MonkeyPatch,
    decision: NewsRelevanceDecision,
) -> None:
    tracker = _install_common_fakes(
        monkeypatch,
        decision=decision,
    )

    result = module.process_news_relevance(str(_INTAKE_ID))

    assert tracker["priority_created"] is True
    assert tracker["priority_enqueued"] is True
    assert result["decision"] == decision.value
    assert result["priority_queue_status"] == "queued"
    assert result["priority_job_id"] == (f"news-priority-{_PRIORITY_ANALYSIS_ID}")


def test_rejected_relevance_does_not_create_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = _install_common_fakes(
        monkeypatch,
        decision=NewsRelevanceDecision.REJECTED,
    )

    monkeypatch.setattr(
        module,
        "create_redis_connection_pool",
        lambda *args, **kwargs: pytest.fail("Rejected relevance must not enqueue priority"),
    )

    result = module.process_news_relevance(str(_INTAKE_ID))

    assert tracker["priority_created"] is False
    assert tracker["priority_enqueued"] is False
    assert result["decision"] == "rejected"
    assert result["priority_queue_status"] == "skipped"
    assert result["priority_job_id"] == ""

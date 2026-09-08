from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

import project_g.interfaces.workers.jobs as jobs
from project_g.domain.news.article_metadata import (
    NewsMetadataStatus,
)
from project_g.domain.news.competition import (
    CompetitionLevel,
)
from project_g.domain.news.evidence_role import (
    EvidenceRole,
)
from project_g.domain.news.priority_analysis import (
    NewsPriorityStatus,
)
from project_g.domain.news.relevance_analysis import (
    NewsRelevanceDecision,
    NewsRelevanceStatus,
)
from project_g.domain.news.script_generation import (
    NewsScriptGeneration,
    NewsScriptGenerationStatus,
)
from project_g.interfaces.workers.jobs import (
    process_news_script,
)

_INTAKE_ID = "2c4c3406-7e28-4207-966e-2cd5dfb5e5e5"


class FakeRepository:
    def __init__(
        self,
        value: object,
    ) -> None:
        self._value = value

    def get_by_intake_id(
        self,
        _intake_id: object,
    ) -> object:
        return self._value


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeGenerateNewsScript:
    def __init__(self) -> None:
        self.input_data: Any = None

    def execute(
        self,
        input_data: Any,
    ) -> SimpleNamespace:
        self.input_data = input_data

        fact = SimpleNamespace(
            text=("2026年8月15日のファーム戦で則本は6回、84球、被安打9だった。"),
            source_id="npb_official",
            source_url=("https://npb.jp/scores_farm/2026/0815/g-a-04/box.html"),
            competition_level=(CompetitionLevel.FARM),
            role=EvidenceRole.TARGET,
        )

        script = SimpleNamespace(
            hook="則本が1軍に合流です。",
            main_narration=("巨人の則本昂大投手が1軍に合流しました。"),
            project_g_comment=("ファームの内容を見ると、手放しで安心とは言いにくいな。"),
            closing="今後の起用に注目です。",
            full_narration=(
                "則本が1軍に合流です。\n\n"
                "巨人の則本昂大投手が"
                "1軍に合流しました。\n\n"
                "ここからはPROJECT Gの見解です。\n\n"
                "ファームの内容を見ると、"
                "手放しで安心とは言いにくいな。\n\n"
                "今後の起用に注目です。"
            ),
        )

        return SimpleNamespace(
            script=script,
            background_facts=(fact,),
        )


def test_process_news_script_rejects_invalid_ranking_score() -> None:
    with pytest.raises(
        ValueError,
        match="ranking_score must be between 0 and 100",
    ):
        process_news_script(
            _INTAKE_ID,
            ranking_score=101,
        )


def test_process_news_script_maps_db_state_to_generation_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_at = datetime(
        2026,
        8,
        22,
        0,
        47,
        tzinfo=UTC,
    )

    intake = SimpleNamespace(
        source_id="hochi_giants_articles",
        canonical_url=("https://hochi.news/articles/20260822-OHT1T51073.html"),
    )

    metadata = SimpleNamespace(
        status=NewsMetadataStatus.EXTRACTED,
        title=("【巨人】則本昂大が１軍合流 東京ドームに姿見せる"),
        description=("巨人の則本昂大投手が２２日、１軍に合流した。"),
        published_at=published_at,
    )

    relevance = SimpleNamespace(
        status=NewsRelevanceStatus.ANALYZED,
        decision=NewsRelevanceDecision.ACCEPTED,
        relevance_score=97,
    )

    priority = SimpleNamespace(
        status=NewsPriorityStatus.ANALYZED,
        priority_score=90,
    )

    events: list[str] = []

    engine = FakeEngine()
    factory = FakeSessionFactory(events)
    service = FakeGenerateNewsScript()
    generation_repository = FakeScriptGenerationRepository(events)
    settings = SimpleNamespace(rq_job_timeout_seconds=300)

    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _settings: engine,
    )
    monkeypatch.setattr(
        jobs,
        "sessionmaker",
        lambda **_kwargs: factory,
    )

    monkeypatch.setattr(
        jobs,
        "SqlAlchemyManualNewsIntakeRepository",
        lambda _session: FakeRepository(intake),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsArticleMetadataRepository",
        lambda _session: FakeRepository(metadata),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsRelevanceAnalysisRepository",
        lambda _session: FakeRepository(relevance),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsPriorityAnalysisRepository",
        lambda _session: FakeRepository(priority),
    )

    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsScriptGenerationRepository",
        lambda _session: generation_repository,
    )

    monkeypatch.setattr(
        jobs,
        "build_generate_news_script",
        lambda **_kwargs: service,
    )

    result = process_news_script(
        _INTAKE_ID,
        ranking_score=88,
    )

    assert isinstance(result, dict)

    assert service.input_data is not None
    assert str(service.input_data.intake_id) == _INTAKE_ID
    assert service.input_data.source_id == "hochi_giants_articles"
    assert service.input_data.published_at == published_at
    assert service.input_data.relevance_score == 97
    assert service.input_data.priority_score == 90
    assert service.input_data.ranking_score == 88

    assert result["status"] == "processed"
    assert result["ranking_score"] == 88
    assert result["evidence_count"] == 1

    evidence = result["evidence"]
    assert isinstance(evidence, list)
    assert evidence[0]["source_id"] == "npb_official"
    assert evidence[0]["competition_level"] == "farm"
    assert evidence[0]["role"] == "target"

    assert engine.disposed is True


class FakeTransactionalContext:
    def __init__(
        self,
        *,
        events: list[str],
        record_transaction: bool,
    ) -> None:
        self._events = events
        self._record_transaction = record_transaction
        self.session = object()

    def __enter__(self) -> object:
        return self.session

    def __exit__(
        self,
        exc_type: object,
        _exc_value: object,
        _traceback: object,
    ) -> None:
        if not self._record_transaction:
            return

        if exc_type is None:
            self._events.append("commit")
        else:
            self._events.append("rollback")


class FakeSessionFactory:
    def __init__(
        self,
        events: list[str],
    ) -> None:
        self._events = events

    def __call__(self) -> FakeTransactionalContext:
        return FakeTransactionalContext(
            events=self._events,
            record_transaction=False,
        )

    def begin(self) -> FakeTransactionalContext:
        return FakeTransactionalContext(
            events=self._events,
            record_transaction=True,
        )


class FakeScriptGenerationRepository:
    def __init__(
        self,
        events: list[str],
    ) -> None:
        self._events = events
        self.generation: NewsScriptGeneration | None = None
        self.claim_started_at: datetime | None = None
        self.claim_stale_before: datetime | None = None

    def get_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
    ) -> NewsScriptGeneration | None:
        generation = self.generation

        if (
            generation is not None
            and generation.intake_id == intake_id
            and generation.generation_version == generation_version
        ):
            return generation

        return None

    def get_by_generation_id(
        self,
        generation_id: UUID,
    ) -> NewsScriptGeneration | None:
        generation = self.generation

        if generation is not None and generation.generation_id == generation_id:
            return generation

        return None

    def add(
        self,
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        self._events.append("prepare")
        self.generation = generation
        return generation

    def claim_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
    ) -> NewsScriptGeneration | None:
        self.claim_started_at = started_at
        self.claim_stale_before = stale_before

        generation = self.get_by_intake_version(
            intake_id=intake_id,
            generation_version=generation_version,
        )

        if generation is None:
            return None

        if generation.status is NewsScriptGenerationStatus.GENERATING:
            if (
                stale_before is None
                or generation.started_at is None
                or generation.started_at > stale_before
            ):
                return None

            claimed = replace(
                generation,
                attempt_count=generation.attempt_count + 1,
                started_at=started_at,
                updated_at=started_at,
            )
        else:
            if generation.status not in {
                NewsScriptGenerationStatus.PENDING,
                NewsScriptGenerationStatus.FAILED,
            }:
                return None

            claimed = generation.start(
                started_at=started_at,
            )

        self._events.append("claim")
        self.generation = claimed
        return claimed

    def update(
        self,
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        self._events.append(f"persist_{generation.status.value}")
        self.generation = generation
        return generation


class EventRecordingGenerateNewsScript(FakeGenerateNewsScript):
    def __init__(
        self,
        events: list[str],
    ) -> None:
        super().__init__()
        self._events = events

    def execute(
        self,
        input_data: Any,
    ) -> SimpleNamespace:
        self._events.append("generate")
        return super().execute(input_data)


def test_process_news_script_commits_claim_before_generation_and_persists_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_at = datetime(
        2026,
        8,
        22,
        0,
        47,
        tzinfo=UTC,
    )

    intake = SimpleNamespace(
        source_id="hochi_giants_articles",
        canonical_url=("https://hochi.news/articles/20260822-OHT1T51073.html"),
    )

    metadata = SimpleNamespace(
        status=NewsMetadataStatus.EXTRACTED,
        title=("【巨人】則本昂大が１軍合流 東京ドームに姿見せる"),
        description=("巨人の則本昂大投手が２２日、１軍に合流した。"),
        published_at=published_at,
    )

    relevance = SimpleNamespace(
        status=NewsRelevanceStatus.ANALYZED,
        decision=NewsRelevanceDecision.ACCEPTED,
        relevance_score=97,
    )

    priority = SimpleNamespace(
        status=NewsPriorityStatus.ANALYZED,
        priority_score=90,
    )

    events: list[str] = []

    engine = FakeEngine()
    factory = FakeSessionFactory(events)
    service = EventRecordingGenerateNewsScript(events)
    generation_repository = FakeScriptGenerationRepository(events)
    settings = SimpleNamespace(rq_job_timeout_seconds=300)

    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _settings: engine,
    )
    monkeypatch.setattr(
        jobs,
        "sessionmaker",
        lambda **_kwargs: factory,
    )

    monkeypatch.setattr(
        jobs,
        "SqlAlchemyManualNewsIntakeRepository",
        lambda _session: FakeRepository(intake),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsArticleMetadataRepository",
        lambda _session: FakeRepository(metadata),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsRelevanceAnalysisRepository",
        lambda _session: FakeRepository(relevance),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsPriorityAnalysisRepository",
        lambda _session: FakeRepository(priority),
    )

    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsScriptGenerationRepository",
        lambda _session: generation_repository,
        raising=False,
    )

    monkeypatch.setattr(
        jobs,
        "build_generate_news_script",
        lambda **_kwargs: service,
    )

    result = process_news_script(
        _INTAKE_ID,
        ranking_score=88,
    )

    generation = generation_repository.generation

    assert generation is not None
    assert generation.status is (NewsScriptGenerationStatus.GENERATED)
    assert generation.ranking_score == 88
    assert generation.attempt_count == 1
    assert generation.evidence_snapshot is not None
    assert len(generation.evidence_snapshot) == 1

    assert events.index("claim") < events.index("commit")
    assert events.index("commit") < events.index("generate")

    assert events.index("generate") < events.index("persist_generated")

    generated_position = events.index("persist_generated")

    assert "commit" in events[generated_position + 1 :]

    assert isinstance(result, dict)
    assert result["status"] == "processed"
    assert result["ranking_score"] == 88
    assert engine.disposed is True


class FailingGenerateNewsScript:
    def __init__(
        self,
        events: list[str],
    ) -> None:
        self._events = events

    def execute(
        self,
        _input_data: Any,
    ) -> None:
        self._events.append("generate")
        raise RuntimeError("script generation failed")


def _patch_ready_script_worker(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[str],
    service: Any,
    generation_repository: FakeScriptGenerationRepository,
) -> FakeEngine:
    published_at = datetime(
        2026,
        8,
        22,
        0,
        47,
        tzinfo=UTC,
    )

    intake = SimpleNamespace(
        source_id="hochi_giants_articles",
        canonical_url=("https://hochi.news/articles/20260822-OHT1T51073.html"),
    )

    metadata = SimpleNamespace(
        status=NewsMetadataStatus.EXTRACTED,
        title=("【巨人】則本昂大が１軍合流 東京ドームに姿見せる"),
        description=("巨人の則本昂大投手が２２日、１軍に合流した。"),
        published_at=published_at,
    )

    relevance = SimpleNamespace(
        status=NewsRelevanceStatus.ANALYZED,
        decision=NewsRelevanceDecision.ACCEPTED,
        relevance_score=97,
    )

    priority = SimpleNamespace(
        status=NewsPriorityStatus.ANALYZED,
        priority_score=90,
    )

    engine = FakeEngine()
    factory = FakeSessionFactory(events)
    settings = SimpleNamespace(rq_job_timeout_seconds=300)

    monkeypatch.setattr(
        jobs,
        "Settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        jobs,
        "create_database_engine",
        lambda _settings: engine,
    )
    monkeypatch.setattr(
        jobs,
        "sessionmaker",
        lambda **_kwargs: factory,
    )

    monkeypatch.setattr(
        jobs,
        "SqlAlchemyManualNewsIntakeRepository",
        lambda _session: FakeRepository(intake),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsArticleMetadataRepository",
        lambda _session: FakeRepository(metadata),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsRelevanceAnalysisRepository",
        lambda _session: FakeRepository(relevance),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsPriorityAnalysisRepository",
        lambda _session: FakeRepository(priority),
    )
    monkeypatch.setattr(
        jobs,
        "SqlAlchemyNewsScriptGenerationRepository",
        lambda _session: generation_repository,
    )

    monkeypatch.setattr(
        jobs,
        "build_generate_news_script",
        lambda **_kwargs: service,
    )

    return engine


def test_process_news_script_persists_failed_state_before_reraising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    generation_repository = FakeScriptGenerationRepository(events)
    service = FailingGenerateNewsScript(events)

    engine = _patch_ready_script_worker(
        monkeypatch,
        events=events,
        service=service,
        generation_repository=generation_repository,
    )

    with pytest.raises(
        RuntimeError,
        match="script generation failed",
    ):
        process_news_script(
            _INTAKE_ID,
            ranking_score=88,
        )

    generation = generation_repository.generation

    assert generation is not None
    assert generation.status is (NewsScriptGenerationStatus.FAILED)
    assert generation.ranking_score == 88
    assert generation.attempt_count == 1
    assert generation.failure_reason == ("RuntimeError: news script generation failed")

    assert events.index("claim") < events.index("commit")
    assert events.index("commit") < events.index("generate")

    assert events.index("generate") < events.index("persist_failed")

    failed_position = events.index("persist_failed")

    assert "commit" in events[failed_position + 1 :]

    assert engine.disposed is True


def test_process_news_script_retries_failed_generation_and_persists_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    generation_repository = FakeScriptGenerationRepository(events)
    failing_service = FailingGenerateNewsScript(events)

    engine = _patch_ready_script_worker(
        monkeypatch,
        events=events,
        service=failing_service,
        generation_repository=generation_repository,
    )

    with pytest.raises(
        RuntimeError,
        match="script generation failed",
    ):
        process_news_script(
            _INTAKE_ID,
            ranking_score=88,
        )

    failed_generation = generation_repository.generation

    assert failed_generation is not None
    assert failed_generation.status is NewsScriptGenerationStatus.FAILED
    assert failed_generation.attempt_count == 1
    assert failed_generation.failure_reason == ("RuntimeError: news script generation failed")

    success_service = EventRecordingGenerateNewsScript(events)

    monkeypatch.setattr(
        jobs,
        "build_generate_news_script",
        lambda **_kwargs: success_service,
    )

    result = process_news_script(
        _INTAKE_ID,
        ranking_score=88,
    )

    generation = generation_repository.generation

    assert generation is not None
    assert generation.status is NewsScriptGenerationStatus.GENERATED
    assert generation.attempt_count == 2
    assert generation.ranking_score == 88
    assert generation.failure_reason is None
    assert generation.evidence_snapshot is not None

    assert events.count("claim") == 2
    assert events.count("generate") == 2
    assert events.count("persist_failed") == 1
    assert events.count("persist_generated") == 1

    assert isinstance(result, dict)
    assert result["status"] == "processed"
    assert result["ranking_score"] == 88
    assert engine.disposed is True


def test_process_news_script_does_not_regenerate_generated_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    generation_repository = FakeScriptGenerationRepository(events)
    service = EventRecordingGenerateNewsScript(events)

    engine = _patch_ready_script_worker(
        monkeypatch,
        events=events,
        service=service,
        generation_repository=generation_repository,
    )

    first = process_news_script(
        _INTAKE_ID,
        ranking_score=88,
    )

    second = process_news_script(
        _INTAKE_ID,
        ranking_score=88,
    )

    generation = generation_repository.generation

    assert generation is not None
    assert generation.status is (NewsScriptGenerationStatus.GENERATED)

    assert isinstance(first, dict)
    assert isinstance(second, dict)

    assert first["status"] == "processed"
    assert second["status"] == "already_generated"

    assert second["ranking_score"] == 88
    assert second["evidence_count"] == 1

    assert events.count("generate") == 1
    assert events.count("persist_generated") == 1

    assert engine.disposed is True


class SecretLeakingGenerateNewsScript:
    def __init__(
        self,
        events: list[str],
    ) -> None:
        self._events = events

    def execute(
        self,
        _input_data: Any,
    ) -> None:
        self._events.append("generate")
        raise RuntimeError("Authorization: Bearer sk-test-secret")


def test_process_news_script_does_not_persist_raw_exception_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    generation_repository = FakeScriptGenerationRepository(events)
    service = SecretLeakingGenerateNewsScript(events)

    engine = _patch_ready_script_worker(
        monkeypatch,
        events=events,
        service=service,
        generation_repository=generation_repository,
    )

    with pytest.raises(RuntimeError):
        process_news_script(
            _INTAKE_ID,
            ranking_score=88,
        )

    generation = generation_repository.generation

    assert generation is not None
    assert generation.status is (NewsScriptGenerationStatus.FAILED)

    assert generation.failure_reason == ("RuntimeError: news script generation failed")
    assert "sk-test-secret" not in generation.failure_reason
    assert "Authorization" not in generation.failure_reason

    assert engine.disposed is True


def test_process_news_script_fresh_generating_returns_delayed_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    generation_repository = FakeScriptGenerationRepository(events)
    service = EventRecordingGenerateNewsScript(events)

    now = datetime.now(UTC)

    generation_repository.generation = NewsScriptGeneration.pending(
        generation_id=UUID("66e8903c-3363-49e7-b45e-694501bbb592"),
        intake_id=UUID(_INTAKE_ID),
        generation_version=1,
        ranking_score=88,
        created_at=now,
    ).start(
        started_at=now,
    )

    engine = _patch_ready_script_worker(
        monkeypatch,
        events=events,
        service=service,
        generation_repository=generation_repository,
    )

    retry_calls: list[dict[str, int]] = []
    retry_sentinel = object()

    def fake_retry(
        **kwargs: int,
    ) -> object:
        retry_calls.append(kwargs)
        return retry_sentinel

    monkeypatch.setattr(
        jobs,
        "Retry",
        fake_retry,
    )

    result = process_news_script(
        _INTAKE_ID,
        ranking_score=88,
    )

    assert result is retry_sentinel
    assert retry_calls == [
        {
            "max": 1,
            "interval": 300,
        }
    ]

    assert generation_repository.claim_started_at is not None
    assert generation_repository.claim_stale_before is not None

    assert (
        generation_repository.claim_started_at - generation_repository.claim_stale_before
    ).total_seconds() == 300

    assert events.count("generate") == 0
    assert engine.disposed is True


def test_process_news_script_reclaims_stale_generating_and_generates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    generation_repository = FakeScriptGenerationRepository(events)
    service = EventRecordingGenerateNewsScript(events)

    now = datetime.now(UTC)

    generation_repository.generation = NewsScriptGeneration.pending(
        generation_id=UUID("a656407d-423e-4efa-9f59-765b35cf6c4c"),
        intake_id=UUID(_INTAKE_ID),
        generation_version=1,
        ranking_score=88,
        created_at=now - timedelta(minutes=11),
    ).start(
        started_at=now - timedelta(minutes=10),
    )

    engine = _patch_ready_script_worker(
        monkeypatch,
        events=events,
        service=service,
        generation_repository=generation_repository,
    )

    result = process_news_script(
        _INTAKE_ID,
        ranking_score=88,
    )

    generation = generation_repository.generation

    assert generation is not None
    assert generation.status is (NewsScriptGenerationStatus.GENERATED)
    assert generation.attempt_count == 2
    assert generation.ranking_score == 88

    assert generation_repository.claim_started_at is not None
    assert generation_repository.claim_stale_before is not None

    assert (
        generation_repository.claim_started_at - generation_repository.claim_stale_before
    ).total_seconds() == 300

    assert events.count("claim") == 1
    assert events.count("generate") == 1
    assert events.count("persist_generated") == 1

    assert isinstance(result, dict)
    assert result["status"] == "processed"
    assert result["ranking_score"] == 88
    assert engine.disposed is True

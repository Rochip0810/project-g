from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

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

    engine = FakeEngine()
    service = FakeGenerateNewsScript()
    settings = SimpleNamespace()

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
        lambda **_kwargs: lambda: nullcontext(object()),
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
        "build_generate_news_script",
        lambda *, session, settings: service,
    )

    result = process_news_script(
        _INTAKE_ID,
        ranking_score=88,
    )

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

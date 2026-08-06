from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.application.news.create_manual_intake import (
    CreateManualNewsIntake,
)
from project_g.application.news.initial_sources import (
    INITIAL_NEWS_SOURCES,
)
from project_g.application.news.manual_url import (
    ManualNewsUrlResolver,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeAlreadyExistsError,
)

_INTAKE_ID = UUID("4ab69a75-31ac-4525-a086-6a828b9c225e")
_SUBMITTED_AT = datetime(
    2026,
    8,
    1,
    12,
    0,
    tzinfo=UTC,
)


class FakeManualNewsIntakeRepository:
    def __init__(self) -> None:
        self._by_canonical_url: dict[
            str,
            ManualNewsIntake,
        ] = {}
        self.added: list[ManualNewsIntake] = []

    def add(
        self,
        intake: ManualNewsIntake,
    ) -> ManualNewsIntake:
        if intake.canonical_url in self._by_canonical_url:
            raise ManualNewsIntakeAlreadyExistsError(intake.canonical_url)

        self._by_canonical_url[intake.canonical_url] = intake
        self.added.append(intake)

        return intake

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> ManualNewsIntake | None:
        return None

    def get_by_canonical_url(
        self,
        canonical_url: str,
    ) -> ManualNewsIntake | None:
        return self._by_canonical_url.get(canonical_url)

    def exists_by_canonical_url(
        self,
        canonical_url: str,
    ) -> bool:
        return canonical_url in self._by_canonical_url


def _service(
    repository: FakeManualNewsIntakeRepository,
) -> CreateManualNewsIntake:
    return CreateManualNewsIntake(
        resolver=ManualNewsUrlResolver(INITIAL_NEWS_SOURCES),
        repository=repository,
        clock=lambda: _SUBMITTED_AT,
        intake_id_factory=lambda: _INTAKE_ID,
    )


def test_service_creates_and_stores_manual_intake() -> None:
    repository = FakeManualNewsIntakeRepository()
    submitted_url = "https://www.giants.jp/news/12345/?utm_source=google&category=team#details"

    intake = _service(repository).execute(submitted_url)

    assert intake.intake_id == _INTAKE_ID
    assert intake.source_id == "giants_official_news"
    assert intake.submitted_url == submitted_url
    assert intake.canonical_url == ("https://www.giants.jp/news/12345/?category=team")
    assert intake.submitted_at == _SUBMITTED_AT
    assert repository.added == [intake]


def test_service_rejects_duplicate_canonical_url() -> None:
    repository = FakeManualNewsIntakeRepository()
    service = _service(repository)

    first = service.execute("https://www.giants.jp/news/12345/?utm_source=google")

    with pytest.raises(
        ManualNewsIntakeAlreadyExistsError,
        match="already exists",
    ):
        service.execute("https://www.giants.jp/news/12345/?fbclid=tracking#details")

    assert len(repository.added) == 1
    assert repository.added[0] == first


def test_service_allows_different_canonical_urls() -> None:
    repository = FakeManualNewsIntakeRepository()
    service = _service(repository)

    first = service.execute("https://www.giants.jp/news/12345/")
    second = service.execute("https://www.giants.jp/news/12346/")

    assert first.canonical_url != second.canonical_url
    assert len(repository.added) == 2

from datetime import UTC, datetime
from uuid import UUID

from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.infrastructure.database.base import Base
from project_g.infrastructure.database.models.manual_news_intake import (
    ManualNewsIntakeRecord,
)

_INTAKE_ID = UUID("87bfce73-53cb-47e8-86b8-62277e0ea397")
_SUBMITTED_AT = datetime(
    2026,
    8,
    1,
    12,
    30,
    tzinfo=UTC,
)


def _intake() -> ManualNewsIntake:
    return ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="giants_official_news",
        submitted_url=("https://www.giants.jp/news/12345/?utm_source=google"),
        canonical_url="https://www.giants.jp/news/12345/",
        submitted_at=_SUBMITTED_AT,
    )


def test_manual_news_intake_table_is_registered() -> None:
    assert "manual_news_intakes" in Base.metadata.tables


def test_manual_news_intake_record_round_trip() -> None:
    intake = _intake()

    record = ManualNewsIntakeRecord.from_domain(intake)

    assert record.intake_id == intake.intake_id
    assert record.source_id == intake.source_id
    assert record.submitted_url == intake.submitted_url
    assert record.canonical_url == intake.canonical_url
    assert record.submitted_at == intake.submitted_at
    assert record.to_domain() == intake

from datetime import UTC, datetime
from uuid import UUID

import pytest

from project_g.domain.news.manual_intake import (
    InvalidManualNewsIntakeError,
    ManualNewsIntake,
)

_INTAKE_ID = UUID("1af69c17-52ae-4b56-87e9-b9d231a1a47d")


def test_manual_news_intake_accepts_valid_metadata() -> None:
    submitted_at = datetime(2026, 8, 1, 10, 30, tzinfo=UTC)

    intake = ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="giants_official_news",
        submitted_url=("https://www.giants.jp/news/12345/?utm_source=alert"),
        canonical_url="https://www.giants.jp/news/12345/",
        submitted_at=submitted_at,
    )

    assert intake.intake_id == _INTAKE_ID
    assert intake.source_id == "giants_official_news"
    assert intake.submitted_at == submitted_at


@pytest.mark.parametrize(
    "source_id",
    [
        "",
        "GiantsOfficial",
        "giants-official",
        " giants_official",
    ],
)
def test_manual_news_intake_rejects_invalid_source_id(
    source_id: str,
) -> None:
    with pytest.raises(InvalidManualNewsIntakeError):
        ManualNewsIntake(
            intake_id=_INTAKE_ID,
            source_id=source_id,
            submitted_url="https://www.giants.jp/news/12345/",
            canonical_url="https://www.giants.jp/news/12345/",
            submitted_at=datetime.now(UTC),
        )


def test_manual_news_intake_rejects_non_https_url() -> None:
    with pytest.raises(
        InvalidManualNewsIntakeError,
        match="submitted_url must use HTTPS",
    ):
        ManualNewsIntake(
            intake_id=_INTAKE_ID,
            source_id="giants_official_news",
            submitted_url="http://www.giants.jp/news/12345/",
            canonical_url="https://www.giants.jp/news/12345/",
            submitted_at=datetime.now(UTC),
        )


def test_manual_news_intake_rejects_url_credentials() -> None:
    with pytest.raises(
        InvalidManualNewsIntakeError,
        match="must not include credentials",
    ):
        ManualNewsIntake(
            intake_id=_INTAKE_ID,
            source_id="giants_official_news",
            submitted_url=("https://user:password@www.giants.jp/news/12345/"),
            canonical_url="https://www.giants.jp/news/12345/",
            submitted_at=datetime.now(UTC),
        )


def test_manual_news_intake_rejects_canonical_fragment() -> None:
    with pytest.raises(
        InvalidManualNewsIntakeError,
        match="canonical_url must not include a fragment",
    ):
        ManualNewsIntake(
            intake_id=_INTAKE_ID,
            source_id="giants_official_news",
            submitted_url=("https://www.giants.jp/news/12345/#details"),
            canonical_url=("https://www.giants.jp/news/12345/#details"),
            submitted_at=datetime.now(UTC),
        )


def test_manual_news_intake_rejects_naive_datetime() -> None:
    with pytest.raises(
        InvalidManualNewsIntakeError,
        match="submitted_at must be timezone-aware",
    ):
        ManualNewsIntake(
            intake_id=_INTAKE_ID,
            source_id="giants_official_news",
            submitted_url="https://www.giants.jp/news/12345/",
            canonical_url="https://www.giants.jp/news/12345/",
            submitted_at=datetime(2026, 8, 1, 10, 30),
        )

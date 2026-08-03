from datetime import UTC, datetime
from io import StringIO
from uuid import UUID

import pytest

from project_g.domain.news.manual_intake import ManualNewsIntake
from project_g.interfaces.management.submit_news_url import (
    parse_arguments,
    print_intake,
)

_INTAKE_ID = UUID("19e78508-577e-44ea-a304-7d5ee9d0716d")
_SUBMITTED_AT = datetime(
    2026,
    8,
    3,
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


def test_parse_arguments_accepts_url() -> None:
    arguments = parse_arguments(["https://www.giants.jp/news/12345/"])

    assert arguments.url == ("https://www.giants.jp/news/12345/")


def test_parse_arguments_requires_url() -> None:
    with pytest.raises(SystemExit):
        parse_arguments([])


def test_print_intake_displays_created_record() -> None:
    output = StringIO()

    print_intake(
        _intake(),
        output=output,
    )

    text = output.getvalue()

    assert "status=created" in text
    assert f"intake_id={_INTAKE_ID}" in text
    assert "source_id=giants_official_news" in text
    assert "canonical_url=https://www.giants.jp/news/12345/" in text
    assert "submitted_at=2026-08-03T12:30:00+00:00" in text

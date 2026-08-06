from argparse import ArgumentTypeError
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

import pytest

from project_g.application.news.complete_metadata_enrichment import (
    NewsMetadataEnrichmentResult,
)
from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.interfaces.management.set_news_metadata import (
    parse_arguments,
    parse_published_at,
    print_result,
)

_INTAKE_ID = UUID("2f9f0dde-47a4-4344-ab5b-294d1037ccfa")
_METADATA_ID = UUID("0989675e-84bd-47e1-aacb-14370390c59c")
_JOB_ID = UUID("50b60e32-a84f-45b6-9677-80e648bcfef6")

_CREATED_AT = datetime(
    2026,
    8,
    5,
    12,
    0,
    tzinfo=UTC,
)
_UPDATED_AT = _CREATED_AT + timedelta(minutes=1)
_PUBLISHED_AT = datetime(
    2026,
    8,
    5,
    9,
    0,
    tzinfo=UTC,
)


def test_parse_arguments_accepts_manual_metadata() -> None:
    arguments = parse_arguments(
        [
            str(_INTAKE_ID),
            "--title",
            "Giants roster announcement",
            "--published-at",
            "2026-08-05T18:00:00+09:00",
            "--description",
            "Official announcement.",
        ]
    )

    assert arguments.intake_id == _INTAKE_ID
    assert arguments.title == ("Giants roster announcement")
    assert arguments.published_at == _PUBLISHED_AT
    assert arguments.description == ("Official announcement.")


def test_parse_published_at_accepts_z_timezone() -> None:
    parsed = parse_published_at("2026-08-05T09:00:00Z")

    assert parsed == _PUBLISHED_AT


def test_parse_published_at_rejects_naive_datetime() -> None:
    with pytest.raises(
        ArgumentTypeError,
        match="timezone",
    ):
        parse_published_at("2026-08-05T18:00:00")


def test_print_result_displays_updated_records() -> None:
    metadata = NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    ).record_manual(
        title="Manual Giants title",
        published_at=_PUBLISHED_AT,
        description="Manual description.",
        updated_at=_UPDATED_AT,
    )

    processing_job = (
        NewsProcessingJob.pending(
            job_id=_JOB_ID,
            intake_id=_INTAKE_ID,
            created_at=_CREATED_AT,
        )
        .start(started_at=_UPDATED_AT)
        .complete(completed_at=_UPDATED_AT)
    )

    output = StringIO()

    print_result(
        NewsMetadataEnrichmentResult(
            metadata=metadata,
            processing_job=processing_job,
        ),
        output=output,
    )

    text = output.getvalue()

    assert "status=updated" in text
    assert f"intake_id={_INTAKE_ID}" in text
    assert f"article_metadata_id={_METADATA_ID}" in text
    assert "article_metadata_status=manual" in text
    assert "title=Manual Giants title" in text
    assert "processing_status=completed" in text

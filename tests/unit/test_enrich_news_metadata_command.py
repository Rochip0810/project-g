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
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.domain.news.processing_job import (
    NewsProcessingJob,
)
from project_g.interfaces.management.enrich_news_metadata import (
    NewsMetadataIntakeNotFoundError,
    NewsMetadataSourceNotConfiguredError,
    get_allowed_hosts,
    load_intake,
    parse_arguments,
    print_result,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeAlreadyExistsError,
)

_INTAKE_ID = UUID("aa0c514c-94ce-45a2-a945-7c50ce02ff3a")
_METADATA_ID = UUID("530eca7b-012f-4b28-a853-38ca13ae69c6")
_JOB_ID = UUID("d6738993-3334-492e-b003-d09ef06713da")

_CREATED_AT = datetime(
    2026,
    8,
    5,
    12,
    0,
    tzinfo=UTC,
)
_COMPLETED_AT = _CREATED_AT + timedelta(minutes=1)


class FakeManualNewsIntakeRepository:
    def __init__(
        self,
        intake: ManualNewsIntake | None,
    ) -> None:
        self.intake = intake

    def add(
        self,
        intake: ManualNewsIntake,
    ) -> ManualNewsIntake:
        if self.intake is not None:
            raise ManualNewsIntakeAlreadyExistsError(intake.canonical_url)

        self.intake = intake
        return intake

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> ManualNewsIntake | None:
        if self.intake is not None and self.intake.intake_id == intake_id:
            return self.intake

        return None

    def get_by_canonical_url(
        self,
        canonical_url: str,
    ) -> ManualNewsIntake | None:
        if self.intake is not None and self.intake.canonical_url == canonical_url:
            return self.intake

        return None

    def exists_by_canonical_url(
        self,
        canonical_url: str,
    ) -> bool:
        return self.get_by_canonical_url(canonical_url) is not None


def _intake() -> ManualNewsIntake:
    return ManualNewsIntake(
        intake_id=_INTAKE_ID,
        source_id="giants_official_news",
        submitted_url=("https://www.giants.jp/news/123456/"),
        canonical_url=("https://www.giants.jp/news/123456/"),
        submitted_at=_CREATED_AT,
    )


def test_parse_arguments_accepts_intake_id() -> None:
    arguments = parse_arguments([str(_INTAKE_ID)])

    assert arguments.intake_id == _INTAKE_ID


def test_load_intake_returns_registered_intake() -> None:
    intake = _intake()

    loaded = load_intake(
        repository=(FakeManualNewsIntakeRepository(intake)),
        intake_id=_INTAKE_ID,
    )

    assert loaded == intake


def test_load_intake_rejects_unknown_id() -> None:
    with pytest.raises(NewsMetadataIntakeNotFoundError):
        load_intake(
            repository=(FakeManualNewsIntakeRepository(None)),
            intake_id=_INTAKE_ID,
        )


def test_allowed_hosts_are_source_specific() -> None:
    assert get_allowed_hosts("giants_official_news") == frozenset(
        {
            "www.giants.jp",
            "giants.jp",
        }
    )


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(NewsMetadataSourceNotConfiguredError):
        get_allowed_hosts("unknown_source")


def test_print_result_displays_extracted_metadata() -> None:
    metadata = NewsArticleMetadata.pending(
        metadata_id=_METADATA_ID,
        intake_id=_INTAKE_ID,
        created_at=_CREATED_AT,
    ).record_extracted(
        title="Giants extracted title",
        published_at=None,
        description="Extracted description.",
        updated_at=_COMPLETED_AT,
    )

    job = (
        NewsProcessingJob.pending(
            job_id=_JOB_ID,
            intake_id=_INTAKE_ID,
            created_at=_CREATED_AT,
        )
        .start(started_at=_COMPLETED_AT)
        .complete(completed_at=_COMPLETED_AT)
    )

    output = StringIO()

    print_result(
        NewsMetadataEnrichmentResult(
            metadata=metadata,
            processing_job=job,
        ),
        output=output,
    )

    text = output.getvalue()

    assert "status=processed" in text
    assert "article_metadata_status=extracted" in text
    assert "title=Giants extracted title" in text
    assert "processing_status=completed" in text
    assert "failure_reason=" in text

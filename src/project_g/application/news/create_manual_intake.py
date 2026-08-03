from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from project_g.application.news.manual_url import (
    ManualNewsUrlResolver,
)
from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeAlreadyExistsError,
    ManualNewsIntakeRepository,
)

Clock = Callable[[], datetime]
IntakeIdFactory = Callable[[], UUID]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreateManualNewsIntake:
    def __init__(
        self,
        *,
        resolver: ManualNewsUrlResolver,
        repository: ManualNewsIntakeRepository,
        clock: Clock = _utc_now,
        intake_id_factory: IntakeIdFactory = uuid4,
    ) -> None:
        self._resolver = resolver
        self._repository = repository
        self._clock = clock
        self._intake_id_factory = intake_id_factory

    def execute(
        self,
        submitted_url: str,
    ) -> ManualNewsIntake:
        resolved = self._resolver.resolve(submitted_url)

        if self._repository.exists_by_canonical_url(resolved.canonical_url):
            raise ManualNewsIntakeAlreadyExistsError(resolved.canonical_url)

        intake = ManualNewsIntake(
            intake_id=self._intake_id_factory(),
            source_id=resolved.source.source_id,
            submitted_url=resolved.submitted_url,
            canonical_url=resolved.canonical_url,
            submitted_at=self._clock(),
        )

        return self._repository.add(intake)

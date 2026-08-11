from dataclasses import dataclass
from typing import Protocol

from project_g.application.news.register_collected_item import (
    CollectedNewsRegistrationStatus,
    RegisterCollectedNewsItemResult,
)
from project_g.domain.news import (
    CollectedNewsItem,
    CollectionResult,
    CollectionStatus,
)


class CollectedNewsItemRegistrar(Protocol):
    def execute(
        self,
        item: CollectedNewsItem,
    ) -> RegisterCollectedNewsItemResult: ...


class CollectionRegistrationFailedError(RuntimeError):
    """Raised when a failed collection cannot be registered."""

    def __init__(
        self,
        result: CollectionResult,
    ) -> None:
        failure = result.failure
        message = failure.message if failure is not None else "Collection failed"

        super().__init__(message)
        self.result = result


@dataclass(frozen=True, slots=True)
class RegisterCollectionResultSummary:
    source_id: str
    discovered_count: int
    registered_count: int
    duplicate_count: int
    registrations: tuple[
        RegisterCollectedNewsItemResult,
        ...,
    ]

    @property
    def registered_items(
        self,
    ) -> tuple[RegisterCollectedNewsItemResult, ...]:
        return tuple(
            registration
            for registration in self.registrations
            if registration.status is CollectedNewsRegistrationStatus.REGISTERED
        )


class RegisterCollectionResult:
    def __init__(
        self,
        *,
        registrar: CollectedNewsItemRegistrar,
    ) -> None:
        self._registrar = registrar

    def execute(
        self,
        result: CollectionResult,
    ) -> RegisterCollectionResultSummary:
        if result.status is CollectionStatus.FAILED:
            raise CollectionRegistrationFailedError(result)

        registrations = tuple(self._registrar.execute(item) for item in result.items)

        registered_count = sum(
            registration.status is CollectedNewsRegistrationStatus.REGISTERED
            for registration in registrations
        )
        duplicate_count = sum(
            registration.status is CollectedNewsRegistrationStatus.DUPLICATE
            for registration in registrations
        )

        return RegisterCollectionResultSummary(
            source_id=result.source.source_id,
            discovered_count=len(result.items),
            registered_count=registered_count,
            duplicate_count=duplicate_count,
            registrations=registrations,
        )

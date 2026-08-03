from typing import Protocol

from project_g.domain.news.manual_intake import ManualNewsIntake


class ManualNewsIntakeAlreadyExistsError(RuntimeError):
    """Raised when the canonical URL is already registered."""

    def __init__(self, canonical_url: str) -> None:
        super().__init__(f"Manual news intake already exists: {canonical_url}")
        self.canonical_url = canonical_url


class ManualNewsIntakeRepository(Protocol):
    def add(
        self,
        intake: ManualNewsIntake,
    ) -> ManualNewsIntake:
        """Store and return a manual news intake."""
        ...

    def get_by_canonical_url(
        self,
        canonical_url: str,
    ) -> ManualNewsIntake | None:
        """Return an intake matching the canonical URL."""
        ...

    def exists_by_canonical_url(
        self,
        canonical_url: str,
    ) -> bool:
        """Return whether the canonical URL is registered."""
        ...

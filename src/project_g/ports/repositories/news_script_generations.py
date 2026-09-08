from datetime import datetime
from typing import Protocol
from uuid import UUID

from project_g.domain.news.script_generation import (
    NewsScriptGeneration,
)


class NewsScriptGenerationAlreadyExistsError(RuntimeError):
    """Raised when the same intake/version already exists."""

    def __init__(
        self,
        intake_id: UUID,
        generation_version: int,
    ) -> None:
        super().__init__(
            f"Script generation already exists for intake/version: {intake_id}/{generation_version}"
        )
        self.intake_id = intake_id
        self.generation_version = generation_version


class NewsScriptGenerationNotFoundError(RuntimeError):
    """Raised when a script-generation record cannot be found."""

    def __init__(
        self,
        generation_id: UUID,
    ) -> None:
        super().__init__(f"Script generation was not found: {generation_id}")
        self.generation_id = generation_id


class NewsScriptGenerationRepository(Protocol):
    def add(
        self,
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        """Store and return a new script generation."""
        ...

    def update(
        self,
        generation: NewsScriptGeneration,
    ) -> NewsScriptGeneration:
        """Update and return an existing script generation."""
        ...

    def get_by_generation_id(
        self,
        generation_id: UUID,
    ) -> NewsScriptGeneration | None:
        """Return a generation by its primary key."""
        ...

    def get_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
    ) -> NewsScriptGeneration | None:
        """Return a generation for one intake/version pair."""
        ...

    def claim_by_intake_version(
        self,
        *,
        intake_id: UUID,
        generation_version: int,
        started_at: datetime,
        stale_before: datetime | None = None,
    ) -> NewsScriptGeneration | None:
        """Atomically claim a ready or stale generation."""
        ...

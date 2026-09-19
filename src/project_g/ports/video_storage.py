from dataclasses import dataclass
from typing import Protocol


class VideoStorageConflictError(RuntimeError):
    """Raised when one storage key already contains different bytes."""


@dataclass(frozen=True, slots=True)
class StoredVideoArtifact:
    storage_key: str
    byte_size: int
    content_sha256: str


class VideoStorage(Protocol):
    def get(
        self,
        *,
        storage_key: str,
    ) -> StoredVideoArtifact | None:
        """Return metadata for an existing durable artifact."""
        ...

    def write(
        self,
        *,
        storage_key: str,
        data: bytes,
    ) -> StoredVideoArtifact:
        """Durably store one video artifact."""
        ...

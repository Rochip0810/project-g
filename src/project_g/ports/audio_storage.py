from dataclasses import dataclass
from typing import Protocol


class AudioStorageConflictError(RuntimeError):
    """Raised when one storage key already contains different bytes."""


@dataclass(frozen=True, slots=True)
class StoredAudioArtifact:
    storage_key: str
    byte_size: int
    content_sha256: str


class AudioStorage(Protocol):
    def get(
        self,
        *,
        storage_key: str,
    ) -> StoredAudioArtifact | None:
        """Return metadata for an existing durable artifact."""
        ...

    def read(
        self,
        *,
        storage_key: str,
    ) -> bytes | None:
        """Return durable audio bytes when the artifact exists."""
        ...

    def write(
        self,
        *,
        storage_key: str,
        data: bytes,
    ) -> StoredAudioArtifact:
        """Durably store one audio artifact."""
        ...

import hashlib
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4

from project_g.ports.audio_storage import (
    AudioStorage,
    AudioStorageConflictError,
    StoredAudioArtifact,
)


class LocalFileAudioStorage(AudioStorage):
    def __init__(
        self,
        *,
        root_directory: str | Path,
    ) -> None:
        self._root = Path(root_directory).resolve()
        self._root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def get(
        self,
        *,
        storage_key: str,
    ) -> StoredAudioArtifact | None:
        target = self._target_for_key(storage_key)

        if not target.is_file():
            return None

        data = target.read_bytes()

        if not data:
            raise AudioStorageConflictError(
                f"Audio storage key contains empty content: {storage_key}"
            )

        return StoredAudioArtifact(
            storage_key=storage_key,
            byte_size=len(data),
            content_sha256=hashlib.sha256(data).hexdigest(),
        )

    def write(
        self,
        *,
        storage_key: str,
        data: bytes,
    ) -> StoredAudioArtifact:
        if not data:
            raise ValueError("Audio data must not be empty")

        target = self._target_for_key(storage_key)
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        content_sha256 = hashlib.sha256(data).hexdigest()

        existing = self._existing_artifact(
            target=target,
            storage_key=storage_key,
            expected_sha256=content_sha256,
        )

        if existing is not None:
            return existing

        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")

        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                # Hard-linking is atomic and never overwrites
                # an existing canonical artifact.
                os.link(
                    temporary,
                    target,
                )
            except FileExistsError:
                existing = self._existing_artifact(
                    target=target,
                    storage_key=storage_key,
                    expected_sha256=content_sha256,
                )

                if existing is None:
                    raise RuntimeError(
                        "Audio artifact disappeared during concurrent storage"
                    ) from None

                return existing

            self._fsync_directory(target.parent)

            return StoredAudioArtifact(
                storage_key=storage_key,
                byte_size=len(data),
                content_sha256=content_sha256,
            )
        finally:
            temporary.unlink(missing_ok=True)

    def _target_for_key(
        self,
        storage_key: str,
    ) -> Path:
        normalized = storage_key.strip()

        if not normalized or "\\" in normalized:
            raise ValueError("Invalid audio storage key")

        relative = PurePosixPath(normalized)

        if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
            raise ValueError("Audio storage key must be a safe relative path")

        target = self._root.joinpath(*relative.parts).resolve()

        if not target.is_relative_to(self._root):
            raise ValueError("Audio storage key escapes root")

        return target

    def _existing_artifact(
        self,
        *,
        target: Path,
        storage_key: str,
        expected_sha256: str,
    ) -> StoredAudioArtifact | None:
        if not target.exists():
            return None

        existing_data = target.read_bytes()
        existing_sha256 = hashlib.sha256(existing_data).hexdigest()

        if existing_sha256 != expected_sha256:
            raise AudioStorageConflictError(
                f"Audio storage key already contains different content: {storage_key}"
            )

        return StoredAudioArtifact(
            storage_key=storage_key,
            byte_size=len(existing_data),
            content_sha256=existing_sha256,
        )

    @staticmethod
    def _fsync_directory(
        directory: Path,
    ) -> None:
        descriptor = os.open(
            directory,
            os.O_RDONLY,
        )

        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

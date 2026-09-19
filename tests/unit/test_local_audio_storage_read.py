from pathlib import Path

import pytest

from project_g.infrastructure.storage.local_audio import (
    LocalFileAudioStorage,
)
from project_g.ports.audio_storage import AudioStorageConflictError


def test_read_returns_stored_audio_bytes(
    tmp_path: Path,
) -> None:
    storage = LocalFileAudioStorage(root_directory=tmp_path)
    data = b"project-g-audio"

    storage.write(
        storage_key="media/audio/example/v1.mp3",
        data=data,
    )

    assert storage.read(storage_key="media/audio/example/v1.mp3") == data


def test_read_returns_none_for_missing_audio(
    tmp_path: Path,
) -> None:
    storage = LocalFileAudioStorage(root_directory=tmp_path)

    assert storage.read(storage_key="media/audio/missing/v1.mp3") is None


def test_read_rejects_empty_existing_audio(
    tmp_path: Path,
) -> None:
    storage = LocalFileAudioStorage(root_directory=tmp_path)

    target = tmp_path / "media/audio/example/v1.mp3"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"")

    with pytest.raises(
        AudioStorageConflictError,
        match="contains empty content",
    ):
        storage.read(storage_key="media/audio/example/v1.mp3")

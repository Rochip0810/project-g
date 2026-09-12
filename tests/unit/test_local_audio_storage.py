import hashlib

import pytest

from project_g.infrastructure.storage.local_audio import (
    LocalFileAudioStorage,
)
from project_g.ports.audio_storage import (
    AudioStorageConflictError,
)


def test_write_persists_audio_and_metadata(
    tmp_path: object,
) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    storage = LocalFileAudioStorage(root_directory=root)
    data = b"project-g-mp3"

    result = storage.write(
        storage_key=("media/audio/production-1/v1.mp3"),
        data=data,
    )

    target = root / "media" / "audio" / "production-1" / "v1.mp3"

    assert target.read_bytes() == data
    assert result.storage_key == ("media/audio/production-1/v1.mp3")
    assert result.byte_size == len(data)
    assert result.content_sha256 == (hashlib.sha256(data).hexdigest())


def test_write_same_content_is_idempotent(
    tmp_path: object,
) -> None:
    from pathlib import Path

    storage = LocalFileAudioStorage(root_directory=Path(str(tmp_path)))
    key = "media/audio/a/v1.mp3"

    first = storage.write(
        storage_key=key,
        data=b"same",
    )
    second = storage.write(
        storage_key=key,
        data=b"same",
    )

    assert second == first


def test_write_different_content_conflicts(
    tmp_path: object,
) -> None:
    from pathlib import Path

    storage = LocalFileAudioStorage(root_directory=Path(str(tmp_path)))
    key = "media/audio/a/v1.mp3"

    storage.write(
        storage_key=key,
        data=b"first",
    )

    with pytest.raises(AudioStorageConflictError):
        storage.write(
            storage_key=key,
            data=b"second",
        )


@pytest.mark.parametrize(
    "storage_key",
    (
        "",
        "../escape.mp3",
        "/absolute.mp3",
        "media\\escape.mp3",
        "media/../escape.mp3",
    ),
)
def test_write_rejects_unsafe_storage_key(
    tmp_path: object,
    storage_key: str,
) -> None:
    from pathlib import Path

    storage = LocalFileAudioStorage(root_directory=Path(str(tmp_path)))

    with pytest.raises(ValueError):
        storage.write(
            storage_key=storage_key,
            data=b"audio",
        )


def test_write_rejects_empty_audio(
    tmp_path: object,
) -> None:
    from pathlib import Path

    storage = LocalFileAudioStorage(root_directory=Path(str(tmp_path)))

    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        storage.write(
            storage_key=("media/audio/a/v1.mp3"),
            data=b"",
        )


def test_get_returns_existing_audio_metadata(
    tmp_path: object,
) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    storage = LocalFileAudioStorage(root_directory=root)

    key = "media/audio/a/v1.mp3"
    data = b"existing-audio"

    storage.write(
        storage_key=key,
        data=data,
    )

    result = storage.get(
        storage_key=key,
    )

    assert result is not None
    assert result.storage_key == key
    assert result.byte_size == len(data)
    assert result.content_sha256 == (hashlib.sha256(data).hexdigest())


def test_get_returns_none_when_artifact_is_missing(
    tmp_path: object,
) -> None:
    from pathlib import Path

    storage = LocalFileAudioStorage(root_directory=Path(str(tmp_path)))

    result = storage.get(
        storage_key="media/audio/a/v1.mp3",
    )

    assert result is None


def test_get_rejects_empty_existing_artifact(
    tmp_path: object,
) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    storage = LocalFileAudioStorage(root_directory=root)

    target = root / "media" / "audio" / "a" / "v1.mp3"

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_bytes(b"")

    with pytest.raises(
        AudioStorageConflictError,
        match="empty content",
    ):
        storage.get(
            storage_key="media/audio/a/v1.mp3",
        )


def test_get_rejects_unsafe_storage_key(
    tmp_path: object,
) -> None:
    from pathlib import Path

    storage = LocalFileAudioStorage(root_directory=Path(str(tmp_path)))

    with pytest.raises(ValueError):
        storage.get(
            storage_key="../escape.mp3",
        )

import hashlib
from pathlib import Path

import pytest

from project_g.infrastructure.storage.local_video import (
    LocalFileVideoStorage,
)
from project_g.ports.video_storage import (
    VideoStorageConflictError,
)

_STORAGE_KEY = "media/video/example/v1.mp4"
_VIDEO_BYTES = b"project-g-video"
_OTHER_VIDEO_BYTES = b"different-video"


def test_write_persists_video_and_returns_metadata(
    tmp_path: Path,
) -> None:
    storage = LocalFileVideoStorage(root_directory=tmp_path)

    artifact = storage.write(
        storage_key=_STORAGE_KEY,
        data=_VIDEO_BYTES,
    )

    assert artifact.storage_key == _STORAGE_KEY
    assert artifact.byte_size == len(_VIDEO_BYTES)
    assert artifact.content_sha256 == hashlib.sha256(_VIDEO_BYTES).hexdigest()

    assert (tmp_path / "media/video/example/v1.mp4").read_bytes() == _VIDEO_BYTES


def test_get_returns_existing_artifact_metadata(
    tmp_path: Path,
) -> None:
    target = tmp_path / "media/video/example/v1.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(_VIDEO_BYTES)

    storage = LocalFileVideoStorage(root_directory=tmp_path)

    artifact = storage.get(storage_key=_STORAGE_KEY)

    assert artifact is not None
    assert artifact.storage_key == _STORAGE_KEY
    assert artifact.byte_size == len(_VIDEO_BYTES)
    assert artifact.content_sha256 == hashlib.sha256(_VIDEO_BYTES).hexdigest()


def test_get_returns_none_when_artifact_does_not_exist(
    tmp_path: Path,
) -> None:
    storage = LocalFileVideoStorage(root_directory=tmp_path)

    assert storage.get(storage_key=_STORAGE_KEY) is None


def test_rewriting_same_content_is_idempotent(
    tmp_path: Path,
) -> None:
    storage = LocalFileVideoStorage(root_directory=tmp_path)

    first = storage.write(
        storage_key=_STORAGE_KEY,
        data=_VIDEO_BYTES,
    )
    second = storage.write(
        storage_key=_STORAGE_KEY,
        data=_VIDEO_BYTES,
    )

    assert second == first


def test_rewriting_different_content_is_rejected(
    tmp_path: Path,
) -> None:
    storage = LocalFileVideoStorage(root_directory=tmp_path)

    storage.write(
        storage_key=_STORAGE_KEY,
        data=_VIDEO_BYTES,
    )

    with pytest.raises(
        VideoStorageConflictError,
        match="already contains different content",
    ):
        storage.write(
            storage_key=_STORAGE_KEY,
            data=_OTHER_VIDEO_BYTES,
        )


def test_write_rejects_empty_video(
    tmp_path: Path,
) -> None:
    storage = LocalFileVideoStorage(root_directory=tmp_path)

    with pytest.raises(
        ValueError,
        match="Video data must not be empty",
    ):
        storage.write(
            storage_key=_STORAGE_KEY,
            data=b"",
        )


def test_get_rejects_empty_existing_artifact(
    tmp_path: Path,
) -> None:
    target = tmp_path / "media/video/example/v1.mp4"
    target.parent.mkdir(parents=True)
    target.touch()

    storage = LocalFileVideoStorage(root_directory=tmp_path)

    with pytest.raises(
        VideoStorageConflictError,
        match="contains empty content",
    ):
        storage.get(storage_key=_STORAGE_KEY)


@pytest.mark.parametrize(
    "storage_key",
    [
        "",
        "../outside.mp4",
        "/absolute.mp4",
        "media/../outside.mp4",
        r"media\video\example.mp4",
    ],
)
def test_storage_key_must_be_safe_relative_path(
    tmp_path: Path,
    storage_key: str,
) -> None:
    storage = LocalFileVideoStorage(root_directory=tmp_path)

    with pytest.raises(ValueError):
        storage.write(
            storage_key=storage_key,
            data=_VIDEO_BYTES,
        )

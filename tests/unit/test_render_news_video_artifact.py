import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from project_g.application.news.render_news_video_artifact import (
    RenderNewsVideoArtifact,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
)
from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
)
from project_g.ports.audio_storage import (
    StoredAudioArtifact,
)
from project_g.ports.video import (
    RenderedVideo,
    VideoRenderRequest,
)
from project_g.ports.video_storage import (
    StoredVideoArtifact,
)

_BASE_TIME = datetime(
    2026,
    9,
    19,
    0,
    0,
    tzinfo=UTC,
)

_MEDIA_ID = UUID("11111111-1111-4111-8111-000000000301")

_AUDIO_ID = UUID("11111111-1111-4111-8111-000000000401")

_VIDEO_ID = UUID("11111111-1111-4111-8111-000000000501")

_AUDIO_DATA = b"project-g-test-audio"
_VIDEO_DATA = b"project-g-test-video"

_AUDIO_HASH = hashlib.sha256(_AUDIO_DATA).hexdigest()

_TEXT_HASH = "c" * 64


def _time(minutes: int) -> datetime:
    return _BASE_TIME + timedelta(minutes=minutes)


def _audio(
    *,
    generated: bool = True,
) -> NewsNarrationAudioGeneration:
    pending = NewsNarrationAudioGeneration.pending(
        audio_generation_id=_AUDIO_ID,
        media_production_id=_MEDIA_ID,
        audio_version=1,
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="marin",
        audio_format="mp3",
        source_text_sha256=_TEXT_HASH,
        created_at=_time(1),
    )

    if not generated:
        return pending

    return pending.start(
        started_at=_time(2),
    ).record_generated(
        storage_key=f"media/audio/{_MEDIA_ID}/v1.mp3",
        byte_size=len(_AUDIO_DATA),
        content_sha256=_AUDIO_HASH,
        completed_at=_time(3),
    )


def _video(
    *,
    started: bool = True,
) -> NewsVideoGeneration:
    pending = NewsVideoGeneration.pending(
        video_generation_id=_VIDEO_ID,
        media_production_id=_MEDIA_ID,
        video_version=1,
        renderer="ffmpeg",
        video_format="mp4",
        width=1080,
        height=1920,
        fps=30,
        source_audio_generation_id=_AUDIO_ID,
        source_audio_sha256=_AUDIO_HASH,
        created_at=_time(4),
    )

    if not started:
        return pending

    return pending.start(
        started_at=_time(5),
    )


class FakeAudioStorage:
    def __init__(
        self,
        data: bytes | None = _AUDIO_DATA,
    ) -> None:
        self.data = data
        self.read_calls: list[str] = []

    def read(
        self,
        *,
        storage_key: str,
    ) -> bytes | None:
        self.read_calls.append(storage_key)
        return self.data

    def get(
        self,
        *,
        storage_key: str,
    ) -> StoredAudioArtifact | None:
        if self.data is None:
            return None

        return StoredAudioArtifact(
            storage_key=storage_key,
            byte_size=len(self.data),
            content_sha256=hashlib.sha256(self.data).hexdigest(),
        )

    def write(
        self,
        *,
        storage_key: str,
        data: bytes,
    ) -> StoredAudioArtifact:
        raise AssertionError("Video rendering must not write source audio")


class FakeVideoStorage:
    def __init__(self) -> None:
        self.writes: list[tuple[str, bytes]] = []

    def get(
        self,
        *,
        storage_key: str,
    ) -> StoredVideoArtifact | None:
        return None

    def write(
        self,
        *,
        storage_key: str,
        data: bytes,
    ) -> StoredVideoArtifact:
        self.writes.append((storage_key, data))

        return StoredVideoArtifact(
            storage_key=storage_key,
            byte_size=len(data),
            content_sha256=hashlib.sha256(data).hexdigest(),
        )


class FakeVideoRenderer:
    def __init__(
        self,
        *,
        fail: bool = False,
    ) -> None:
        self.fail = fail
        self.requests: list[VideoRenderRequest] = []

    def render(
        self,
        request: VideoRenderRequest,
    ) -> RenderedVideo:
        self.requests.append(request)

        if self.fail:
            raise RuntimeError("Simulated FFmpeg failure")

        return RenderedVideo(
            data=_VIDEO_DATA,
            duration_ms=12000,
        )


def _service(
    *,
    audio_data: bytes | None = _AUDIO_DATA,
    render_failure: bool = False,
) -> tuple[
    RenderNewsVideoArtifact,
    FakeAudioStorage,
    FakeVideoStorage,
    FakeVideoRenderer,
]:
    audio_storage = FakeAudioStorage(
        data=audio_data,
    )

    video_storage = FakeVideoStorage()

    renderer = FakeVideoRenderer(
        fail=render_failure,
    )

    service = RenderNewsVideoArtifact(
        audio_storage=audio_storage,
        video_storage=video_storage,
        renderer=renderer,
    )

    return (
        service,
        audio_storage,
        video_storage,
        renderer,
    )


def test_render_generates_video_from_verified_audio() -> None:
    service, audio_storage, video_storage, renderer = _service()

    result = service.execute(
        generation=_video(),
        source_audio=_audio(),
        expected_attempt_number=1,
    )

    expected_audio_key = f"media/audio/{_MEDIA_ID}/v1.mp3"

    expected_video_key = f"media/video/{_MEDIA_ID}/v1/a1.mp4"

    assert audio_storage.read_calls == [expected_audio_key]

    assert renderer.requests == [
        VideoRenderRequest(
            audio_data=_AUDIO_DATA,
            audio_format="mp3",
            video_format="mp4",
            width=1080,
            height=1920,
            fps=30,
        )
    ]

    assert video_storage.writes == [
        (
            expected_video_key,
            _VIDEO_DATA,
        )
    ]

    assert result.storage_key == expected_video_key
    assert result.byte_size == len(_VIDEO_DATA)

    assert result.content_sha256 == hashlib.sha256(_VIDEO_DATA).hexdigest()

    assert result.duration_ms == 12000


def test_render_uses_attempt_specific_storage_key() -> None:
    service, _, video_storage, _ = _service()

    generation = replace(
        _video(),
        attempt_count=2,
    )

    result = service.execute(
        generation=generation,
        source_audio=_audio(),
        expected_attempt_number=2,
    )

    expected_key = f"media/video/{_MEDIA_ID}/v1/a2.mp4"

    assert result.storage_key == expected_key

    assert video_storage.writes == [
        (
            expected_key,
            _VIDEO_DATA,
        )
    ]


def test_render_rejects_pending_video() -> None:
    service, audio_storage, video_storage, renderer = _service()

    with pytest.raises(
        RuntimeError,
        match="Video generation must be generating",
    ):
        service.execute(
            generation=_video(started=False),
            source_audio=_audio(),
            expected_attempt_number=1,
        )

    assert audio_storage.read_calls == []
    assert renderer.requests == []
    assert video_storage.writes == []


def test_render_rejects_invalid_attempt_number() -> None:
    service, audio_storage, video_storage, renderer = _service()

    with pytest.raises(
        ValueError,
        match="expected_attempt_number must be at least 1",
    ):
        service.execute(
            generation=_video(),
            source_audio=_audio(),
            expected_attempt_number=0,
        )

    assert audio_storage.read_calls == []
    assert renderer.requests == []
    assert video_storage.writes == []


def test_render_rejects_unfinished_audio() -> None:
    service, audio_storage, video_storage, renderer = _service()

    with pytest.raises(
        RuntimeError,
        match="Source audio must be generated",
    ):
        service.execute(
            generation=_video(),
            source_audio=_audio(generated=False),
            expected_attempt_number=1,
        )

    assert audio_storage.read_calls == []
    assert renderer.requests == []
    assert video_storage.writes == []


def test_render_rejects_wrong_audio_generation_id() -> None:
    service, audio_storage, video_storage, renderer = _service()

    wrong_audio = replace(
        _audio(),
        audio_generation_id=UUID("11111111-1111-4111-8111-000000000999"),
    )

    with pytest.raises(
        RuntimeError,
        match="Source audio generation ID does not match",
    ):
        service.execute(
            generation=_video(),
            source_audio=wrong_audio,
            expected_attempt_number=1,
        )

    assert audio_storage.read_calls == []
    assert renderer.requests == []
    assert video_storage.writes == []


def test_render_rejects_missing_audio_artifact() -> None:
    service, audio_storage, video_storage, renderer = _service(audio_data=None)

    with pytest.raises(
        RuntimeError,
        match="Source audio artifact was not found",
    ):
        service.execute(
            generation=_video(),
            source_audio=_audio(),
            expected_attempt_number=1,
        )

    assert len(audio_storage.read_calls) == 1
    assert renderer.requests == []
    assert video_storage.writes == []


def test_render_rejects_corrupted_audio_artifact() -> None:
    service, audio_storage, video_storage, renderer = _service(audio_data=b"corrupted-audio-data")

    with pytest.raises(
        RuntimeError,
        match="Source audio artifact SHA-256 does not match",
    ):
        service.execute(
            generation=_video(),
            source_audio=_audio(),
            expected_attempt_number=1,
        )

    assert len(audio_storage.read_calls) == 1
    assert renderer.requests == []
    assert video_storage.writes == []


def test_render_failure_does_not_write_video() -> None:
    service, audio_storage, video_storage, renderer = _service(render_failure=True)

    with pytest.raises(
        RuntimeError,
        match="Simulated FFmpeg failure",
    ):
        service.execute(
            generation=_video(),
            source_audio=_audio(),
            expected_attempt_number=1,
        )

    assert len(audio_storage.read_calls) == 1
    assert len(renderer.requests) == 1
    assert video_storage.writes == []

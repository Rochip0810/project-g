import hashlib
from dataclasses import dataclass

from project_g.domain.news.narration_audio import (
    NewsNarrationAudioGeneration,
    NewsNarrationAudioStatus,
)
from project_g.domain.news.video_generation import (
    NewsVideoGeneration,
    NewsVideoGenerationStatus,
)
from project_g.ports.audio_storage import AudioStorage
from project_g.ports.video import VideoRenderer, VideoRenderRequest
from project_g.ports.video_storage import VideoStorage


@dataclass(frozen=True, slots=True)
class RenderedNewsVideoArtifact:
    storage_key: str
    byte_size: int
    content_sha256: str
    duration_ms: int


class RenderNewsVideoArtifact:
    def __init__(
        self,
        *,
        audio_storage: AudioStorage,
        video_storage: VideoStorage,
        renderer: VideoRenderer,
    ) -> None:
        self._audio_storage = audio_storage
        self._video_storage = video_storage
        self._renderer = renderer

    def execute(
        self,
        *,
        generation: NewsVideoGeneration,
        source_audio: NewsNarrationAudioGeneration,
        expected_attempt_number: int,
    ) -> RenderedNewsVideoArtifact:

        # -------------------------------------------------
        # 1. Validate the claimed generation
        # -------------------------------------------------

        if generation.status is not NewsVideoGenerationStatus.GENERATING:
            raise RuntimeError("Video generation must be generating")

        if expected_attempt_number < 1:
            raise ValueError("expected_attempt_number must be at least 1")

        if generation.attempt_count != expected_attempt_number:
            raise RuntimeError("Video generation attempt does not match")

        if generation.renderer != "ffmpeg":
            raise RuntimeError("Unsupported video renderer")

        # -------------------------------------------------
        # 2. Validate the source audio
        # -------------------------------------------------

        if source_audio.status is not NewsNarrationAudioStatus.GENERATED:
            raise RuntimeError("Source audio must be generated")

        if source_audio.audio_generation_id != generation.source_audio_generation_id:
            raise RuntimeError("Source audio generation ID does not match")

        if source_audio.media_production_id != generation.media_production_id:
            raise RuntimeError("Source audio media production does not match")

        if source_audio.content_sha256 != generation.source_audio_sha256:
            raise RuntimeError("Source audio metadata hash does not match")

        if source_audio.storage_key is None:
            raise RuntimeError("Source audio has no storage key")

        # -------------------------------------------------
        # 3. Read and verify the actual audio bytes
        # -------------------------------------------------

        audio_data = self._audio_storage.read(
            storage_key=source_audio.storage_key,
        )

        if audio_data is None:
            raise RuntimeError("Source audio artifact was not found")

        actual_audio_sha256 = hashlib.sha256(audio_data).hexdigest()

        if actual_audio_sha256 != generation.source_audio_sha256:
            raise RuntimeError("Source audio artifact SHA-256 does not match")

        # -------------------------------------------------
        # 4. Render MP4
        # -------------------------------------------------

        rendered = self._renderer.render(
            VideoRenderRequest(
                audio_data=audio_data,
                audio_format=source_audio.audio_format,
                video_format=generation.video_format,
                width=generation.width,
                height=generation.height,
                fps=generation.fps,
            )
        )

        # -------------------------------------------------
        # 5. Store the artifact under this attempt's key
        # -------------------------------------------------

        storage_key = (
            f"media/video/{generation.media_production_id}/"
            f"v{generation.video_version}/"
            f"a{expected_attempt_number}.{generation.video_format}"
        )

        artifact = self._video_storage.write(
            storage_key=storage_key,
            data=rendered.data,
        )

        return RenderedNewsVideoArtifact(
            storage_key=artifact.storage_key,
            byte_size=artifact.byte_size,
            content_sha256=artifact.content_sha256,
            duration_ms=rendered.duration_ms,
        )

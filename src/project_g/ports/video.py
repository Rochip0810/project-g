from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VideoRenderRequest:
    audio_data: bytes
    audio_format: str
    video_format: str
    width: int
    height: int
    fps: int


@dataclass(frozen=True, slots=True)
class RenderedVideo:
    data: bytes
    duration_ms: int


class VideoRenderer(Protocol):
    def render(
        self,
        request: VideoRenderRequest,
    ) -> RenderedVideo:
        """Render one video artifact from narration audio."""
        ...

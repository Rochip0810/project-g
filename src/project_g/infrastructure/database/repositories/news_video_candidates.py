from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from project_g.domain.news.media_production import (
    InvalidNewsMediaProductionError,
    NewsMediaProductionStatus,
)
from project_g.domain.news.narration_audio import (
    InvalidNewsNarrationAudioError,
    NewsNarrationAudioStatus,
)
from project_g.domain.news.video_generation import (
    NewsVideoGenerationStatus,
)
from project_g.infrastructure.database.models import (
    NewsMediaProductionRecord,
    NewsNarrationAudioGenerationRecord,
    NewsVideoGenerationRecord,
)
from project_g.ports.repositories.news_video_candidates import (
    NewsVideoCandidate,
)


class SqlAlchemyNewsVideoCandidateRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def list_candidates(
        self,
        *,
        audio_version: int,
        video_version: int,
        stale_before: datetime,
        limit: int,
    ) -> tuple[NewsVideoCandidate, ...]:
        if audio_version < 1:
            raise ValueError("audio_version must be at least 1")

        if video_version < 1:
            raise ValueError("video_version must be at least 1")

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        if stale_before.tzinfo is None or stale_before.utcoffset() is None:
            raise ValueError("stale_before must be timezone-aware")

        audio_join = and_(
            NewsNarrationAudioGenerationRecord.media_production_id
            == NewsMediaProductionRecord.media_production_id,
            NewsNarrationAudioGenerationRecord.audio_version == audio_version,
        )

        video_join = and_(
            NewsVideoGenerationRecord.media_production_id
            == NewsMediaProductionRecord.media_production_id,
            NewsVideoGenerationRecord.video_version == video_version,
        )

        eligible_video = or_(
            NewsVideoGenerationRecord.video_generation_id.is_(None),
            NewsVideoGenerationRecord.status.in_(
                (
                    NewsVideoGenerationStatus.PENDING.value,
                    NewsVideoGenerationStatus.FAILED.value,
                )
            ),
            and_(
                NewsVideoGenerationRecord.status == NewsVideoGenerationStatus.GENERATING.value,
                NewsVideoGenerationRecord.started_at.is_not(None),
                NewsVideoGenerationRecord.started_at <= stale_before,
            ),
        )

        statement = (
            select(
                NewsMediaProductionRecord,
                NewsNarrationAudioGenerationRecord,
            )
            .join(
                NewsNarrationAudioGenerationRecord,
                audio_join,
            )
            .outerjoin(
                NewsVideoGenerationRecord,
                video_join,
            )
            .where(
                NewsMediaProductionRecord.status.in_(
                    (
                        NewsMediaProductionStatus.PROCESSING.value,
                        NewsMediaProductionStatus.FAILED.value,
                    )
                ),
                NewsNarrationAudioGenerationRecord.status
                == NewsNarrationAudioStatus.GENERATED.value,
                NewsNarrationAudioGenerationRecord.storage_key.is_not(None),
                NewsNarrationAudioGenerationRecord.content_sha256.is_not(None),
                eligible_video,
            )
            .order_by(
                NewsMediaProductionRecord.created_at.asc(),
                NewsMediaProductionRecord.media_production_id.asc(),
            )
        )

        candidates: list[NewsVideoCandidate] = []

        for media_record, audio_record in self._session.execute(statement):
            try:
                production = media_record.to_domain()
                audio = audio_record.to_domain()
            except (
                InvalidNewsMediaProductionError,
                InvalidNewsNarrationAudioError,
            ):
                continue

            candidates.append(
                NewsVideoCandidate(
                    media_production=production,
                    source_audio=audio,
                )
            )

            if len(candidates) >= limit:
                break

        return tuple(candidates)

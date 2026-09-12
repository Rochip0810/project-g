from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from project_g.domain.news.media_production import (
    InvalidNewsMediaProductionError,
    NewsMediaProductionStatus,
)
from project_g.domain.news.narration_audio import (
    NewsNarrationAudioStatus,
)
from project_g.domain.news.script_generation import (
    NewsScriptGenerationStatus,
)
from project_g.infrastructure.database.models import (
    NewsMediaProductionRecord,
    NewsNarrationAudioGenerationRecord,
    NewsScriptGenerationRecord,
)
from project_g.ports.repositories.news_narration_audio_candidates import (
    NewsNarrationAudioCandidate,
)


class SqlAlchemyNewsNarrationAudioCandidateRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def list_candidates(
        self,
        *,
        audio_version: int,
        stale_before: datetime,
        limit: int,
    ) -> tuple[NewsNarrationAudioCandidate, ...]:
        if audio_version < 1:
            raise ValueError("audio_version must be at least 1")

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        if stale_before.tzinfo is None or stale_before.utcoffset() is None:
            raise ValueError("stale_before must be timezone-aware")

        audio_join = and_(
            NewsNarrationAudioGenerationRecord.media_production_id
            == NewsMediaProductionRecord.media_production_id,
            NewsNarrationAudioGenerationRecord.audio_version == audio_version,
        )

        eligible_audio = or_(
            NewsNarrationAudioGenerationRecord.audio_generation_id.is_(None),
            NewsNarrationAudioGenerationRecord.status.in_(
                (
                    NewsNarrationAudioStatus.PENDING.value,
                    NewsNarrationAudioStatus.FAILED.value,
                )
            ),
            and_(
                NewsNarrationAudioGenerationRecord.status
                == NewsNarrationAudioStatus.GENERATING.value,
                NewsNarrationAudioGenerationRecord.started_at.is_not(None),
                NewsNarrationAudioGenerationRecord.started_at <= stale_before,
            ),
        )

        statement = (
            select(
                NewsMediaProductionRecord,
                NewsScriptGenerationRecord.full_narration,
            )
            .join(
                NewsScriptGenerationRecord,
                NewsScriptGenerationRecord.generation_id
                == NewsMediaProductionRecord.script_generation_id,
            )
            .outerjoin(
                NewsNarrationAudioGenerationRecord,
                audio_join,
            )
            .where(
                NewsMediaProductionRecord.status.in_(
                    (
                        NewsMediaProductionStatus.PENDING.value,
                        NewsMediaProductionStatus.PROCESSING.value,
                        NewsMediaProductionStatus.FAILED.value,
                    )
                ),
                NewsScriptGenerationRecord.status == NewsScriptGenerationStatus.GENERATED.value,
                NewsScriptGenerationRecord.full_narration.is_not(None),
                NewsScriptGenerationRecord.full_narration != "",
                eligible_audio,
            )
            .order_by(
                NewsMediaProductionRecord.created_at.asc(),
                NewsMediaProductionRecord.media_production_id.asc(),
            )
        )

        candidates: list[NewsNarrationAudioCandidate] = []

        for record, full_narration in self._session.execute(statement):
            if not isinstance(full_narration, str) or not full_narration.strip():
                continue

            try:
                production = record.to_domain()
            except InvalidNewsMediaProductionError:
                continue

            candidates.append(
                NewsNarrationAudioCandidate(
                    media_production=production,
                    full_narration=full_narration.strip(),
                )
            )

            if len(candidates) >= limit:
                break

        return tuple(candidates)

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from project_g.domain.news.script_generation import (
    InvalidNewsScriptGenerationError,
    NewsScriptGeneration,
    NewsScriptGenerationStatus,
)
from project_g.infrastructure.database.models import (
    NewsMediaProductionRecord,
    NewsScriptGenerationRecord,
)


class SqlAlchemyNewsMediaIntakeCandidateRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def list_candidates(
        self,
        *,
        media_version: int,
        limit: int,
    ) -> tuple[NewsScriptGeneration, ...]:
        existing_media = exists().where(
            NewsMediaProductionRecord.script_generation_id
            == NewsScriptGenerationRecord.generation_id,
            NewsMediaProductionRecord.media_version == media_version,
        )

        statement = (
            select(NewsScriptGenerationRecord)
            .where(
                NewsScriptGenerationRecord.status == NewsScriptGenerationStatus.GENERATED.value,
                NewsScriptGenerationRecord.attempt_count >= 1,
                NewsScriptGenerationRecord.started_at.is_not(None),
                NewsScriptGenerationRecord.completed_at.is_not(None),
                NewsScriptGenerationRecord.hook.is_not(None),
                func.length(func.trim(NewsScriptGenerationRecord.hook)) > 0,
                NewsScriptGenerationRecord.main_narration.is_not(None),
                func.length(func.trim(NewsScriptGenerationRecord.main_narration)) > 0,
                NewsScriptGenerationRecord.project_g_comment.is_not(None),
                func.length(func.trim(NewsScriptGenerationRecord.project_g_comment)) > 0,
                NewsScriptGenerationRecord.closing.is_not(None),
                func.length(func.trim(NewsScriptGenerationRecord.closing)) > 0,
                NewsScriptGenerationRecord.full_narration.is_not(None),
                func.length(func.trim(NewsScriptGenerationRecord.full_narration)) > 0,
                NewsScriptGenerationRecord.evidence_snapshot.is_not(None),
                ~existing_media,
            )
            .order_by(
                NewsScriptGenerationRecord.completed_at.asc(),
                NewsScriptGenerationRecord.generation_id.asc(),
            )
        )

        records = self._session.scalars(statement)

        candidates: list[NewsScriptGeneration] = []

        for record in records:
            try:
                candidate = record.to_domain()
            except InvalidNewsScriptGenerationError:
                continue

            candidates.append(candidate)

            if len(candidates) >= limit:
                break

        return tuple(candidates)

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_g.domain.news.article_metadata import (
    NewsArticleMetadata,
)
from project_g.infrastructure.database.models import (
    NewsArticleMetadataRecord,
)
from project_g.ports.repositories.news_article_metadata import (
    NewsArticleMetadataAlreadyExistsError,
    NewsArticleMetadataNotFoundError,
)


class SqlAlchemyNewsArticleMetadataRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        if self.get_by_intake_id(metadata.intake_id) is not None:
            raise NewsArticleMetadataAlreadyExistsError(metadata.intake_id)

        record = NewsArticleMetadataRecord.from_domain(metadata)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsArticleMetadataAlreadyExistsError(metadata.intake_id) from error

        return record.to_domain()

    def update(
        self,
        metadata: NewsArticleMetadata,
    ) -> NewsArticleMetadata:
        record = self._session.get(
            NewsArticleMetadataRecord,
            metadata.metadata_id,
        )

        if record is None or record.intake_id != metadata.intake_id:
            raise NewsArticleMetadataNotFoundError(metadata.metadata_id)

        record.status = metadata.status.value
        record.title = metadata.title
        record.published_at = metadata.published_at
        record.description = metadata.description
        record.failure_reason = metadata.failure_reason
        record.created_at = metadata.created_at
        record.updated_at = metadata.updated_at

        self._session.flush()

        return record.to_domain()

    def get_by_metadata_id(
        self,
        metadata_id: UUID,
    ) -> NewsArticleMetadata | None:
        record = self._session.get(
            NewsArticleMetadataRecord,
            metadata_id,
        )

        if record is None:
            return None

        return record.to_domain()

    def get_by_intake_id(
        self,
        intake_id: UUID,
    ) -> NewsArticleMetadata | None:
        statement = select(NewsArticleMetadataRecord).where(
            NewsArticleMetadataRecord.intake_id == intake_id
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()

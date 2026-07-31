from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
)
from project_g.infrastructure.database.models import (
    NewsSourceRecord,
)
from project_g.ports.repositories import (
    NewsSourceAlreadyExistsError,
    StoredNewsSourceNotFoundError,
)


class SqlAlchemyNewsSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, source: NewsSource) -> NewsSource:
        if self.get_by_source_id(source.source_id) is not None:
            raise NewsSourceAlreadyExistsError(source.source_id)

        record = NewsSourceRecord.from_domain(source)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise NewsSourceAlreadyExistsError(source.source_id) from error

        return record.to_domain()

    def get_by_source_id(
        self,
        source_id: str,
    ) -> NewsSource | None:
        statement = select(NewsSourceRecord).where(NewsSourceRecord.source_id == source_id)
        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()

    def list_all(self) -> tuple[NewsSource, ...]:
        statement = select(NewsSourceRecord).order_by(NewsSourceRecord.source_id.asc())

        return tuple(record.to_domain() for record in self._session.scalars(statement))

    def list_collectable(self) -> tuple[NewsSource, ...]:
        statement = (
            select(NewsSourceRecord)
            .where(NewsSourceRecord.status == SourceStatus.ENABLED.value)
            .order_by(
                NewsSourceRecord.is_official.desc(),
                NewsSourceRecord.priority.desc(),
                func.lower(NewsSourceRecord.name).asc(),
                NewsSourceRecord.source_id.asc(),
            )
        )

        return tuple(record.to_domain() for record in self._session.scalars(statement))

    def update_status(
        self,
        source_id: str,
        status: SourceStatus,
    ) -> NewsSource:
        statement = select(NewsSourceRecord).where(NewsSourceRecord.source_id == source_id)
        record = self._session.scalar(statement)

        if record is None:
            raise StoredNewsSourceNotFoundError(source_id)

        record.status = status.value
        record.updated_at = datetime.now(UTC)
        self._session.flush()

        return record.to_domain()

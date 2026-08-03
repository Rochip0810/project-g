from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_g.domain.news.manual_intake import (
    ManualNewsIntake,
)
from project_g.infrastructure.database.models import (
    ManualNewsIntakeRecord,
)
from project_g.ports.repositories.manual_news_intakes import (
    ManualNewsIntakeAlreadyExistsError,
)


class SqlAlchemyManualNewsIntakeRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        intake: ManualNewsIntake,
    ) -> ManualNewsIntake:
        if self.exists_by_canonical_url(intake.canonical_url):
            raise ManualNewsIntakeAlreadyExistsError(intake.canonical_url)

        record = ManualNewsIntakeRecord.from_domain(intake)

        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise ManualNewsIntakeAlreadyExistsError(intake.canonical_url) from error

        return record.to_domain()

    def get_by_canonical_url(
        self,
        canonical_url: str,
    ) -> ManualNewsIntake | None:
        statement = select(ManualNewsIntakeRecord).where(
            ManualNewsIntakeRecord.canonical_url == canonical_url
        )

        record = self._session.scalar(statement)

        if record is None:
            return None

        return record.to_domain()

    def exists_by_canonical_url(
        self,
        canonical_url: str,
    ) -> bool:
        statement = (
            select(ManualNewsIntakeRecord.intake_id)
            .where(ManualNewsIntakeRecord.canonical_url == canonical_url)
            .limit(1)
        )

        return self._session.scalar(statement) is not None

from collections.abc import Iterable
from dataclasses import replace

from project_g.domain.news import (
    NewsSource,
    SourceStatus,
)


class DuplicateNewsSourceError(ValueError):
    pass


class NewsSourceNotFoundError(KeyError):
    pass


class SourceRegistry:
    def __init__(
        self,
        sources: Iterable[NewsSource] = (),
    ) -> None:
        self._sources: dict[str, NewsSource] = {}

        for source in sources:
            self.register(source)

    def register(self, source: NewsSource) -> None:
        if source.source_id in self._sources:
            raise DuplicateNewsSourceError(f"Source already exists: {source.source_id}")

        self._sources[source.source_id] = source

    def get(self, source_id: str) -> NewsSource:
        try:
            return self._sources[source_id]
        except KeyError as error:
            raise NewsSourceNotFoundError(source_id) from error

    def set_status(
        self,
        source_id: str,
        status: SourceStatus,
    ) -> NewsSource:
        current = self.get(source_id)
        updated = replace(current, status=status)
        self._sources[source_id] = updated

        return updated

    def enable(self, source_id: str) -> NewsSource:
        return self.set_status(
            source_id,
            SourceStatus.ENABLED,
        )

    def pause(self, source_id: str) -> NewsSource:
        return self.set_status(
            source_id,
            SourceStatus.PAUSED,
        )

    def disable(self, source_id: str) -> NewsSource:
        return self.set_status(
            source_id,
            SourceStatus.DISABLED,
        )

    def list_all(self) -> tuple[NewsSource, ...]:
        return tuple(
            sorted(
                self._sources.values(),
                key=lambda source: source.source_id,
            )
        )

    def list_collectable(self) -> tuple[NewsSource, ...]:
        collectable = (source for source in self._sources.values() if source.collectable)

        return tuple(
            sorted(
                collectable,
                key=lambda source: (
                    not source.is_official,
                    -source.priority,
                    source.name.casefold(),
                ),
            )
        )

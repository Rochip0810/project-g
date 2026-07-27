from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from project_g.infrastructure.config import Settings
from project_g.infrastructure.database import (
    check_database_connection,
    create_database_engine,
    is_database_at_head,
)
from project_g.infrastructure.queue import (
    RedisClient,
    check_redis_connection,
    close_redis_client,
    create_redis_client,
    create_redis_connection_pool,
)


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    database: bool
    redis: bool
    migrations: bool

    @property
    def ready(self) -> bool:
        return self.database and self.redis and self.migrations


type ReadinessProbe = Callable[[], ReadinessReport]


@dataclass(slots=True)
class RuntimeHealthResources:
    engine: Engine
    redis_client: RedisClient

    def check(self) -> ReadinessReport:
        database_healthy = check_database_connection(self.engine)
        redis_healthy = check_redis_connection(self.redis_client)
        migrations_current = False

        if database_healthy:
            try:
                migrations_current = is_database_at_head(self.engine)
            except Exception:
                migrations_current = False

        return ReadinessReport(
            database=database_healthy,
            redis=redis_healthy,
            migrations=migrations_current,
        )

    def close(self) -> None:
        close_redis_client(self.redis_client)
        self.engine.dispose()


def create_runtime_health_resources(
    settings: Settings,
) -> RuntimeHealthResources:
    engine = create_database_engine(settings)
    connection_pool = create_redis_connection_pool(settings)
    redis_client = create_redis_client(connection_pool)

    return RuntimeHealthResources(
        engine=engine,
        redis_client=redis_client,
    )

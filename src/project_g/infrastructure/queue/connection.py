from typing import Protocol, cast

from redis import ConnectionPool, Redis
from redis.exceptions import RedisError

from project_g.infrastructure.config import Settings


class RedisClient(Protocol):
    def ping(self) -> bool:
        pass

    def close(self) -> None:
        pass


def create_redis_connection_pool(
    settings: Settings,
    *,
    decode_responses: bool = True,
) -> ConnectionPool:
    return ConnectionPool(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_database,
        decode_responses=decode_responses,
        socket_connect_timeout=(settings.redis_socket_connect_timeout_seconds),
        socket_timeout=settings.redis_socket_timeout_seconds,
        health_check_interval=(settings.redis_health_check_interval_seconds),
        max_connections=settings.redis_max_connections,
        client_name=(f"{settings.app_name}-{settings.app_env.value}"),
    )


def create_redis_client(
    connection_pool: ConnectionPool,
) -> RedisClient:
    client = Redis.from_pool(connection_pool)

    return cast(RedisClient, client)


def check_redis_connection(client: RedisClient) -> bool:
    try:
        return client.ping()
    except RedisError:
        return False


def close_redis_client(client: RedisClient) -> None:
    client.close()


def close_redis_connection_pool(
    connection_pool: ConnectionPool,
) -> None:
    connection_pool.close()

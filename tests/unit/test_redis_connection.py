from typing import cast
from unittest.mock import MagicMock

import pytest
from redis import ConnectionPool
from redis.exceptions import ConnectionError as RedisConnectionError

from project_g.infrastructure.config import AppEnvironment, Settings
from project_g.infrastructure.queue import (
    RedisClient,
    check_redis_connection,
    close_redis_client,
    close_redis_connection_pool,
    create_redis_client,
    create_redis_connection_pool,
)


class HealthyRedisClient:
    def __init__(self) -> None:
        self.closed = False

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        self.closed = True


class UnhealthyRedisClient:
    def ping(self) -> bool:
        raise RedisConnectionError("Redis is unavailable")

    def close(self) -> None:
        pass


def _create_redis_settings() -> Settings:
    return Settings(
        app_env=AppEnvironment.TEST,
        app_name="project-g-test",
        redis_host="redis.example",
        redis_port=6380,
        redis_database=4,
        redis_socket_connect_timeout_seconds=2.5,
        redis_socket_timeout_seconds=3.5,
        redis_health_check_interval_seconds=15,
        redis_max_connections=12,
    )


def test_redis_connection_pool_uses_project_settings() -> None:
    pool = create_redis_connection_pool(_create_redis_settings())

    try:
        connection_kwargs = pool.connection_kwargs

        assert connection_kwargs["host"] == "redis.example"
        assert connection_kwargs["port"] == 6380
        assert connection_kwargs["db"] == 4
        assert connection_kwargs["decode_responses"] is True
        assert connection_kwargs["socket_connect_timeout"] == 2.5
        assert connection_kwargs["socket_timeout"] == 3.5
        assert connection_kwargs["health_check_interval"] == 15
        assert connection_kwargs["client_name"] == ("project-g-test-test")
        assert pool.max_connections == 12
    finally:
        close_redis_connection_pool(pool)


def test_redis_client_can_be_created_without_connecting() -> None:
    pool = create_redis_connection_pool(_create_redis_settings())
    client = create_redis_client(pool)

    close_redis_client(client)


def test_redis_health_check_returns_true_after_ping() -> None:
    client = HealthyRedisClient()

    assert check_redis_connection(client) is True


def test_redis_health_check_returns_false_on_connection_error() -> None:
    client = UnhealthyRedisClient()

    assert check_redis_connection(client) is False


def test_redis_client_can_be_closed() -> None:
    client = HealthyRedisClient()

    close_redis_client(client)

    assert client.closed is True


def test_redis_connection_pool_can_be_closed() -> None:
    pool_mock = MagicMock(spec=ConnectionPool)

    close_redis_connection_pool(cast(ConnectionPool, pool_mock))

    pool_mock.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("redis_socket_connect_timeout_seconds", 0),
        ("redis_socket_timeout_seconds", 0),
        ("redis_max_connections", 0),
    ],
)
def test_invalid_redis_settings_are_rejected(
    field_name: str,
    invalid_value: int,
) -> None:
    with pytest.raises(ValueError):
        Settings.model_validate(
            {
                field_name: invalid_value,
            }
        )


def test_healthy_client_matches_redis_protocol() -> None:
    client: RedisClient = HealthyRedisClient()

    assert client.ping() is True

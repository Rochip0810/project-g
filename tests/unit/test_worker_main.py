from importlib import import_module
from types import SimpleNamespace
from typing import Any

import pytest

worker_main = import_module("project_g.interfaces.workers.main")


class FakeLogger:
    def info(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> None:
        pass


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeWorker:
    def __init__(self) -> None:
        self.work_calls: list[dict[str, object]] = []

    def work(
        self,
        **kwargs: object,
    ) -> None:
        self.work_calls.append(kwargs)


def test_main_runs_worker_with_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        rq_system_queue="system-test",
        rq_default_queue="default-test",
    )

    connection = FakeConnection()
    worker = FakeWorker()
    pool = object()

    class FakeRedis:
        @staticmethod
        def from_pool(
            _pool: object,
        ) -> FakeConnection:
            return connection

    monkeypatch.setattr(
        worker_main,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        worker_main,
        "configure_logging",
        lambda _settings: None,
    )
    monkeypatch.setattr(
        worker_main,
        "get_logger",
        lambda _name: FakeLogger(),
    )
    monkeypatch.setattr(
        worker_main,
        "create_redis_connection_pool",
        lambda *_args, **_kwargs: pool,
    )
    monkeypatch.setattr(
        worker_main,
        "Redis",
        FakeRedis,
    )
    monkeypatch.setattr(
        worker_main,
        "create_worker",
        lambda _settings, _connection: worker,
    )

    worker_main.main()

    assert worker.work_calls == [
        {
            "with_scheduler": True,
        }
    ]
    assert connection.closed is True

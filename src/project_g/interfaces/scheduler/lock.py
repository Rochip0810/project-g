from typing import Any, Protocol

from redis.exceptions import LockNotOwnedError


class SchedulerLock(Protocol):
    def acquire(self) -> bool:
        pass

    def release(self) -> None:
        pass


class RedisSchedulerLock:
    def __init__(
        self,
        connection: Any,
        *,
        key: str,
        timeout_seconds: int,
    ) -> None:
        self._lock = connection.lock(
            name=key,
            timeout=timeout_seconds,
            blocking_timeout=0,
        )
        self._acquired = False

    def acquire(self) -> bool:
        self._acquired = bool(self._lock.acquire(blocking=False))
        return self._acquired

    def release(self) -> None:
        if not self._acquired:
            return

        try:
            self._lock.release()
        except LockNotOwnedError:
            pass
        finally:
            self._acquired = False

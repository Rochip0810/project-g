from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    unbind_contextvars,
)


def bind_log_context(**values: object) -> None:
    bind_contextvars(**values)


def clear_log_context() -> None:
    clear_contextvars()


def unbind_log_context(*keys: str) -> None:
    unbind_contextvars(*keys)

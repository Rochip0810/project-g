import logging
import sys
from collections.abc import Mapping
from typing import Any, TextIO, cast

import structlog
from structlog.typing import EventDict, Processor

from project_g.infrastructure.config import Settings
from project_g.infrastructure.logging.masking import mask_sensitive_data


class AddCommonFields:
    def __init__(self, fields: Mapping[str, str]) -> None:
        self._fields = dict(fields)

    def __call__(
        self,
        _logger: Any,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        for key, value in self._fields.items():
            event_dict.setdefault(key, value)

        return event_dict


def _resolve_log_level(level_name: str) -> int:
    level = logging.getLevelNamesMapping().get(level_name.upper())

    if not isinstance(level, int):
        raise ValueError(f"Unsupported log level: {level_name}")

    return level


def configure_logging(
    settings: Settings,
    *,
    stream: TextIO | None = None,
) -> None:
    level = _resolve_log_level(settings.log_level)

    common_fields = AddCommonFields(
        {
            "environment": settings.app_env.value,
            "application": settings.app_name,
            "version": settings.app_version,
        }
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(
            fmt="iso",
            utc=True,
            key="timestamp",
        ),
        common_fields,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        mask_sensitive_data,
    ]

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(sort_keys=True),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    logging.captureWarnings(True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast(
        structlog.stdlib.BoundLogger,
        structlog.get_logger(name),
    )

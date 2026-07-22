import re
from collections.abc import Mapping
from typing import Any

from structlog.typing import EventDict

MASKED_VALUE = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "database_url",
)

_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)\b("
    r"password|secret|token|api[_-]?key|authorization|cookie"
    r")\b(\s*[:=]\s*)([^\r\n]+)"
)


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.lower().replace("-", "_")
    return any(part in normalized_key for part in _SENSITIVE_KEY_PARTS)


def _redact_text(value: str) -> str:
    return _SENSITIVE_TEXT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{MASKED_VALUE}",
        value,
    )


def _mask_value(value: Any, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return MASKED_VALUE

    if isinstance(value, str):
        return _redact_text(value)

    if isinstance(value, Mapping):
        return {
            str(nested_key): _mask_value(nested_value, str(nested_key))
            for nested_key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [_mask_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_mask_value(item) for item in value)

    return value


def mask_sensitive_data(
    _logger: Any,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    return {key: _mask_value(value, key) for key, value in event_dict.items()}

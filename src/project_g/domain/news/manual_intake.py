import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
_MAX_URL_LENGTH = 2048


class InvalidManualNewsIntakeError(ValueError):
    """Raised when a manual news intake is invalid."""


def _validate_https_url(
    value: str,
    *,
    field_name: str,
    allow_fragment: bool,
) -> None:
    if not value:
        raise InvalidManualNewsIntakeError(f"{field_name} must not be empty")

    if value != value.strip():
        raise InvalidManualNewsIntakeError(f"{field_name} must not contain surrounding whitespace")

    if len(value) > _MAX_URL_LENGTH:
        raise InvalidManualNewsIntakeError(
            f"{field_name} must not exceed {_MAX_URL_LENGTH} characters"
        )

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as error:
        raise InvalidManualNewsIntakeError(f"{field_name} is not a valid URL") from error

    if parsed.scheme.lower() != "https":
        raise InvalidManualNewsIntakeError(f"{field_name} must use HTTPS")

    if hostname is None:
        raise InvalidManualNewsIntakeError(f"{field_name} must include a hostname")

    if parsed.username is not None or parsed.password is not None:
        raise InvalidManualNewsIntakeError(f"{field_name} must not include credentials")

    if not allow_fragment and parsed.fragment:
        raise InvalidManualNewsIntakeError(f"{field_name} must not include a fragment")


@dataclass(frozen=True, slots=True)
class ManualNewsIntake:
    intake_id: UUID
    source_id: str
    submitted_url: str
    canonical_url: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        if not _SOURCE_ID_PATTERN.fullmatch(self.source_id):
            raise InvalidManualNewsIntakeError(
                "source_id must contain only lowercase letters, numbers, and underscores"
            )

        _validate_https_url(
            self.submitted_url,
            field_name="submitted_url",
            allow_fragment=True,
        )
        _validate_https_url(
            self.canonical_url,
            field_name="canonical_url",
            allow_fragment=False,
        )

        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise InvalidManualNewsIntakeError("submitted_at must be timezone-aware")

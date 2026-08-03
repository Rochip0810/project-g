from dataclasses import dataclass
from ipaddress import ip_address
from typing import Final
from urllib.parse import (
    SplitResult,
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

from project_g.domain.news import NewsSource

_MAX_URL_LENGTH: Final = 2048

_TRACKING_PARAMETERS: Final = frozenset(
    {
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
    }
)

_LOCAL_HOST_SUFFIXES: Final = (
    ".internal",
    ".invalid",
    ".lan",
    ".local",
    ".localhost",
    ".test",
)


class ManualNewsUrlError(ValueError):
    """Base error for rejected manual news URLs."""


class UnsafeManualNewsUrlError(ManualNewsUrlError):
    """Raised when a submitted URL is unsafe."""


class UnsupportedNewsSourceError(ManualNewsUrlError):
    """Raised when no registered source matches a URL."""


class AmbiguousNewsSourceError(ManualNewsUrlError):
    """Raised when multiple sources match equally."""


@dataclass(frozen=True, slots=True)
class ResolvedManualNewsUrl:
    source: NewsSource
    submitted_url: str
    canonical_url: str


class ManualNewsUrlResolver:
    def __init__(
        self,
        sources: tuple[NewsSource, ...],
    ) -> None:
        self._sources = sources

    def resolve(
        self,
        submitted_url: str,
    ) -> ResolvedManualNewsUrl:
        parsed = _parse_submitted_url(submitted_url)
        hostname = _normalize_hostname(parsed.hostname)

        source = self._match_source(
            hostname=hostname,
            path=parsed.path or "/",
        )

        canonical_url = _canonicalize_url(
            hostname=hostname,
            path=parsed.path,
            query=parsed.query,
        )

        return ResolvedManualNewsUrl(
            source=source,
            submitted_url=submitted_url,
            canonical_url=canonical_url,
        )

    def _match_source(
        self,
        *,
        hostname: str,
        path: str,
    ) -> NewsSource:
        matches: list[tuple[int, NewsSource]] = []

        for source in self._sources:
            source_url = urlsplit(source.base_url)
            source_hostname = _normalize_hostname(source_url.hostname)

            if source_hostname != hostname:
                continue

            source_path = source_url.path or "/"

            if not _path_matches(
                submitted_path=path,
                source_path=source_path,
            ):
                continue

            matches.append(
                (
                    len(source_path.rstrip("/")),
                    source,
                )
            )

        if not matches:
            raise UnsupportedNewsSourceError("URL does not match a registered news source")

        matches.sort(
            key=lambda item: item[0],
            reverse=True,
        )
        best_path_length = matches[0][0]
        best_matches = [
            source for path_length, source in matches if path_length == best_path_length
        ]

        if len(best_matches) != 1:
            raise AmbiguousNewsSourceError("URL matches multiple registered news sources")

        return best_matches[0]


def _parse_submitted_url(
    value: str,
) -> SplitResult:
    if not value:
        raise UnsafeManualNewsUrlError("URL must not be empty")

    if value != value.strip():
        raise UnsafeManualNewsUrlError("URL must not contain surrounding whitespace")

    if len(value) > _MAX_URL_LENGTH:
        raise UnsafeManualNewsUrlError(f"URL must not exceed {_MAX_URL_LENGTH} characters")

    if "\\" in value:
        raise UnsafeManualNewsUrlError("URL must not contain backslashes")

    if any(ord(character) < 32 for character in value):
        raise UnsafeManualNewsUrlError("URL must not contain control characters")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise UnsafeManualNewsUrlError("URL is invalid") from error

    if parsed.scheme.lower() != "https":
        raise UnsafeManualNewsUrlError("URL must use HTTPS")

    if parsed.hostname is None:
        raise UnsafeManualNewsUrlError("URL must include a hostname")

    if parsed.username is not None or parsed.password is not None:
        raise UnsafeManualNewsUrlError("URL must not include credentials")

    if port not in {None, 443}:
        raise UnsafeManualNewsUrlError("URL must not use a non-standard port")

    _normalize_hostname(parsed.hostname)

    return parsed


def _normalize_hostname(
    hostname: str | None,
) -> str:
    if hostname is None:
        raise UnsafeManualNewsUrlError("URL must include a hostname")

    try:
        normalized = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise UnsafeManualNewsUrlError("URL hostname is invalid") from error

    if not normalized:
        raise UnsafeManualNewsUrlError("URL hostname must not be empty")

    if normalized == "localhost":
        raise UnsafeManualNewsUrlError("Local hostnames are not allowed")

    if normalized.endswith(_LOCAL_HOST_SUFFIXES):
        raise UnsafeManualNewsUrlError("Local or reserved hostnames are not allowed")

    try:
        ip_address(normalized)
    except ValueError:
        return normalized

    raise UnsafeManualNewsUrlError("IP address hosts are not allowed")


def _path_matches(
    *,
    submitted_path: str,
    source_path: str,
) -> bool:
    normalized_source_path = source_path.rstrip("/")

    if not normalized_source_path:
        return True

    return submitted_path == normalized_source_path or submitted_path.startswith(
        f"{normalized_source_path}/"
    )


def _canonicalize_url(
    *,
    hostname: str,
    path: str,
    query: str,
) -> str:
    query_parameters = [
        (key, value)
        for key, value in parse_qsl(
            query,
            keep_blank_values=True,
        )
        if not _is_tracking_parameter(key)
    ]
    query_parameters.sort()

    return urlunsplit(
        (
            "https",
            hostname,
            path or "/",
            urlencode(query_parameters, doseq=True),
            "",
        )
    )


def _is_tracking_parameter(
    key: str,
) -> bool:
    normalized_key = key.lower()

    return normalized_key.startswith("utm_") or normalized_key in _TRACKING_PARAMETERS

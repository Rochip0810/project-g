from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class HttpClientError(RuntimeError):
    pass


class HttpTimeoutError(HttpClientError):
    pass


class HttpRequestError(HttpClientError):
    pass


class HttpDomainNotAllowedError(HttpClientError):
    def __init__(self, url: str) -> None:
        super().__init__(f"HTTP domain is not allowed: {url}")
        self.url = url


class HttpRedirectLimitError(HttpClientError):
    pass


class HttpResponseTooLargeError(HttpClientError):
    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"HTTP response exceeded {limit_bytes} bytes")
        self.limit_bytes = limit_bytes


class HttpStatusError(HttpClientError):
    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"Unexpected HTTP status {status_code}: {url}")
        self.status_code = status_code
        self.url = url


@dataclass(frozen=True, slots=True)
class HttpResponse:
    requested_url: str
    final_url: str
    status_code: int
    headers: Mapping[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    @property
    def content_type(self) -> str:
        return self.headers.get(
            "content-type",
            "",
        ).casefold()


@runtime_checkable
class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
        pass

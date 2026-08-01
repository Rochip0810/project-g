from collections.abc import Callable

import httpx
import pytest

from project_g.infrastructure.http import HttpxHttpClient
from project_g.ports.http import (
    HttpDomainNotAllowedError,
    HttpResponseTooLargeError,
    HttpStatusError,
)

ALLOWED_HOSTS = frozenset(
    {
        "www.giants.jp",
        "giants.jp",
    }
)


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_redirects: int = 3,
) -> HttpxHttpClient:
    return HttpxHttpClient(
        user_agent="ProjectG-Test/0.1",
        max_redirects=max_redirects,
        transport=httpx.MockTransport(handler),
    )


def test_http_client_returns_html_response() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.headers["user-agent"] == ("ProjectG-Test/0.1")

        return httpx.Response(
            200,
            headers={
                "content-type": "text/html; charset=utf-8",
            },
            content=b"<html>Giants</html>",
            request=request,
        )

    response = _client(handler).get(
        "https://www.giants.jp/news/",
        timeout_seconds=5,
        max_response_bytes=10_000,
        allowed_hosts=ALLOWED_HOSTS,
    )

    assert response.status_code == 200
    assert response.text == "<html>Giants</html>"
    assert "text/html" in response.content_type


def test_http_client_follows_approved_redirect() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if request.url.host == "giants.jp":
            return httpx.Response(
                301,
                headers={
                    "location": ("https://www.giants.jp/news/"),
                },
                request=request,
            )

        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html>OK</html>",
            request=request,
        )

    response = _client(handler).get(
        "https://giants.jp/news/",
        timeout_seconds=5,
        max_response_bytes=10_000,
        allowed_hosts=ALLOWED_HOSTS,
    )

    assert response.final_url == ("https://www.giants.jp/news/")


def test_http_client_rejects_external_redirect() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            302,
            headers={
                "location": "https://example.com/news/",
            },
            request=request,
        )

    with pytest.raises(HttpDomainNotAllowedError):
        _client(handler).get(
            "https://www.giants.jp/news/",
            timeout_seconds=5,
            max_response_bytes=10_000,
            allowed_hosts=ALLOWED_HOSTS,
        )


def test_http_client_enforces_response_size_limit() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 101,
            request=request,
        )

    with pytest.raises(HttpResponseTooLargeError):
        _client(handler).get(
            "https://www.giants.jp/news/",
            timeout_seconds=5,
            max_response_bytes=100,
            allowed_hosts=ALLOWED_HOSTS,
        )


def test_http_client_rejects_error_status() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            503,
            request=request,
        )

    with pytest.raises(HttpStatusError) as error:
        _client(handler).get(
            "https://www.giants.jp/news/",
            timeout_seconds=5,
            max_response_bytes=10_000,
            allowed_hosts=ALLOWED_HOSTS,
        )

    assert error.value.status_code == 503


def test_http_client_rejects_unapproved_initial_domain() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        raise AssertionError("External request must not be executed")

    with pytest.raises(HttpDomainNotAllowedError):
        _client(handler).get(
            "https://example.com/news/",
            timeout_seconds=5,
            max_response_bytes=10_000,
            allowed_hosts=ALLOWED_HOSTS,
        )

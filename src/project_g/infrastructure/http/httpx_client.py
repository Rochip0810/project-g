from urllib.parse import urljoin, urlparse

import httpx

from project_g.ports.http import (
    HttpDomainNotAllowedError,
    HttpRedirectLimitError,
    HttpRequestError,
    HttpResponse,
    HttpResponseTooLargeError,
    HttpStatusError,
    HttpTimeoutError,
)


class HttpxHttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        max_redirects: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._max_redirects = max_redirects
        self._transport = transport

    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
        requested_url = url
        current_url = url

        headers = {
            "User-Agent": self._user_agent,
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.1"),
            "Accept-Language": "ja-JP,ja;q=0.9",
        }

        try:
            with httpx.Client(
                headers=headers,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                for redirect_count in range(self._max_redirects + 1):
                    self._validate_url(
                        current_url,
                        allowed_hosts=allowed_hosts,
                    )

                    with client.stream(
                        "GET",
                        current_url,
                        timeout=timeout_seconds,
                    ) as response:
                        if 300 <= response.status_code < 400:
                            location = response.headers.get("location")

                            if location is None:
                                raise HttpStatusError(
                                    response.status_code,
                                    str(response.url),
                                )

                            if redirect_count >= self._max_redirects:
                                raise HttpRedirectLimitError("HTTP redirect limit exceeded")

                            current_url = urljoin(
                                str(response.url),
                                location,
                            )
                            continue

                        if not 200 <= response.status_code < 300:
                            raise HttpStatusError(
                                response.status_code,
                                str(response.url),
                            )

                        body = self._read_limited_body(
                            response,
                            max_response_bytes=(max_response_bytes),
                        )

                        return HttpResponse(
                            requested_url=requested_url,
                            final_url=str(response.url),
                            status_code=response.status_code,
                            headers=dict(response.headers),
                            body=body,
                        )

        except httpx.TimeoutException as error:
            raise HttpTimeoutError(f"HTTP request timed out: {current_url}") from error
        except httpx.RequestError as error:
            raise HttpRequestError(f"HTTP request failed: {current_url}") from error

        raise HttpRedirectLimitError("HTTP redirect processing did not complete")

    @staticmethod
    def _validate_url(
        url: str,
        *,
        allowed_hosts: frozenset[str],
    ) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()

        normalized_allowed_hosts = {allowed_host.casefold() for allowed_host in allowed_hosts}

        if parsed.scheme != "https" or not host or host not in normalized_allowed_hosts:
            raise HttpDomainNotAllowedError(url)

    @staticmethod
    def _read_limited_body(
        response: httpx.Response,
        *,
        max_response_bytes: int,
    ) -> bytes:
        chunks: list[bytes] = []
        total_bytes = 0

        for chunk in response.iter_bytes():
            total_bytes += len(chunk)

            if total_bytes > max_response_bytes:
                raise HttpResponseTooLargeError(max_response_bytes)

            chunks.append(chunk)

        return b"".join(chunks)

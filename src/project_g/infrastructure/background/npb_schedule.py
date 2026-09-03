import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from project_g.ports.http import HttpClient, HttpClientError

_NPB_HOST = "npb.jp"
_NPB_ALLOWED_HOSTS = frozenset({_NPB_HOST})
_JST = ZoneInfo("Asia/Tokyo")

_GAME_PATH_PATTERN = re.compile(
    r"^/"
    r"(?P<competition>scores|scores_farm)/"
    r"(?P<year>\d{4})/"
    r"(?P<month_day>\d{4})/"
    r"(?P<game_slug>[a-z0-9]+-[a-z0-9]+-\d+)/?"
    r"(?:box\.html)?$"
)


def _iter_months(
    start_date: date,
    end_date: date,
) -> tuple[tuple[int, int], ...]:
    year = start_date.year
    month = start_date.month

    months: list[tuple[int, int]] = []

    while (year, month) <= (
        end_date.year,
        end_date.month,
    ):
        months.append((year, month))

        if month == 12:
            year += 1
            month = 1
        else:
            month += 1

    return tuple(months)


class NPBGiantsScheduleParser:
    def parse(
        self,
        *,
        html: str,
        source_url: str,
        published_until: datetime | None = None,
        lookback_days: int = 14,
    ) -> tuple[str, ...]:
        source = urlparse(source_url)

        if source.scheme != "https" or source.hostname != _NPB_HOST:
            raise ValueError("source_url must be an HTTPS npb.jp URL")

        if lookback_days <= 0:
            raise ValueError("lookback_days must be greater than zero")

        window_start: date | None = None
        window_end: date | None = None

        if published_until is not None:
            if published_until.tzinfo is None or published_until.utcoffset() is None:
                raise ValueError("published_until must be timezone-aware")

            window_end = published_until.astimezone(_JST).date()
            window_start = window_end - timedelta(days=lookback_days)

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        urls: list[str] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue

            href = anchor.get("href")
            if not isinstance(href, str):
                continue

            absolute_url = urljoin(
                source_url,
                href,
            )
            parsed = urlparse(absolute_url)

            if parsed.scheme != "https" or parsed.hostname != _NPB_HOST:
                continue

            match = _GAME_PATH_PATTERN.fullmatch(parsed.path)
            if match is None:
                continue

            game_slug = match.group("game_slug")
            team_codes = game_slug.split("-")[:2]

            if "g" not in team_codes:
                continue

            try:
                year = int(match.group("year"))
                month_day = match.group("month_day")
                month = int(month_day[:2])
                day = int(month_day[2:])

                game_date = date(
                    year,
                    month,
                    day,
                )
            except ValueError:
                continue

            if (
                window_start is not None
                and window_end is not None
                and not (window_start <= game_date <= window_end)
            ):
                continue

            box_url = (
                f"https://{_NPB_HOST}/"
                f"{match.group('competition')}/"
                f"{match.group('year')}/"
                f"{match.group('month_day')}/"
                f"{game_slug}/box.html"
            )

            if box_url in seen:
                continue

            seen.add(box_url)
            urls.append(box_url)

        return tuple(urls)


class NPBGiantsGameUrlDiscovery:
    def __init__(
        self,
        *,
        http_client: HttpClient,
        parser: NPBGiantsScheduleParser,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")

        self._http_client = http_client
        self._parser = parser
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    def discover(
        self,
        *,
        published_until: datetime,
        lookback_days: int = 14,
    ) -> tuple[str, ...]:
        if published_until.tzinfo is None or published_until.utcoffset() is None:
            raise ValueError("published_until must be timezone-aware")

        if lookback_days <= 0:
            raise ValueError("lookback_days must be greater than zero")

        window_end = published_until.astimezone(_JST).date()
        window_start = window_end - timedelta(days=lookback_days)

        urls: list[str] = []
        seen: set[str] = set()

        for year, month in _iter_months(
            window_start,
            window_end,
        ):
            schedule_urls = (
                (f"https://{_NPB_HOST}/games/{year}/schedule_{month:02d}_detail.html"),
                (f"https://{_NPB_HOST}/farm/{year}/schedule_{month:02d}_detail.html"),
            )

            for schedule_url in schedule_urls:
                try:
                    response = self._http_client.get(
                        schedule_url,
                        timeout_seconds=self._timeout_seconds,
                        max_response_bytes=self._max_response_bytes,
                        allowed_hosts=_NPB_ALLOWED_HOSTS,
                    )
                except HttpClientError:
                    continue

                discovered = self._parser.parse(
                    html=response.text,
                    source_url=response.final_url,
                    published_until=published_until,
                    lookback_days=lookback_days,
                )

                for url in discovered:
                    if url in seen:
                        continue

                    seen.add(url)
                    urls.append(url)

        return tuple(urls)

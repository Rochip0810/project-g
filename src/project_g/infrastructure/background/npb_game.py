import re
from datetime import date, datetime, time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from project_g.domain.news.competition import CompetitionLevel
from project_g.domain.news.game_evidence import NPBGamePitchingEvidence
from project_g.ports.npb_game import (
    NPBGameEvidenceExtractionError as NPBGameEvidenceExtractionError,
)

_FARM_PATH_PATTERN = re.compile(
    r"^/scores_farm/(?P<year>\d{4})/(?P<month>\d{2})(?P<day>\d{2})/"
    r"[^/]+/box\.html$"
)

_FIRST_TEAM_PATH_PATTERN = re.compile(
    r"^/scores/(?P<year>\d{4})/(?P<month>\d{2})(?P<day>\d{2})/"
    r"[^/]+/box\.html$"
)

_EXPECTED_HEADERS = (
    "投手",
    "投球数",
    "打者",
    "投球回",
    "安打",
    "本塁打",
    "四球",
    "死球",
    "三振",
    "暴投",
    "ボーク",
    "失点",
    "自責点",
)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _parse_int(
    value: str,
    *,
    field_name: str,
) -> int:
    normalized = _normalize_text(value)

    try:
        parsed = int(normalized)
    except ValueError as error:
        raise NPBGameEvidenceExtractionError(
            f"Invalid integer for {field_name}: {normalized!r}"
        ) from error

    if parsed < 0:
        raise NPBGameEvidenceExtractionError(f"Negative value for {field_name}: {parsed}")

    return parsed


def _parse_source_url(
    source_url: str,
) -> tuple[date, CompetitionLevel]:
    parsed = urlparse(source_url)

    if parsed.scheme != "https" or (parsed.hostname or "").casefold() != "npb.jp":
        raise NPBGameEvidenceExtractionError("NPB game evidence URL must use https://npb.jp")

    for pattern, competition_level in (
        (_FARM_PATH_PATTERN, CompetitionLevel.FARM),
        (_FIRST_TEAM_PATH_PATTERN, CompetitionLevel.FIRST_TEAM),
    ):
        match = pattern.fullmatch(parsed.path)

        if match is None:
            continue

        try:
            game_date = date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError as error:
            raise NPBGameEvidenceExtractionError("NPB game URL contains an invalid date") from error

        return game_date, competition_level

    raise NPBGameEvidenceExtractionError("Unsupported NPB game box-score URL")


_JST = ZoneInfo("Asia/Tokyo")

_GAME_END_TIME_PATTERN = re.compile(r"終了\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})")


def _parse_game_ended_at(
    soup: BeautifulSoup,
    *,
    game_date: date,
) -> datetime | None:
    page_text = _normalize_text(soup.get_text(" ", strip=True))

    if "試合終了" not in page_text:
        return None

    match = _GAME_END_TIME_PATTERN.search(page_text)

    if match is None:
        raise NPBGameEvidenceExtractionError(
            "NPB game is marked finished but end time was not found"
        )

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))

    if hour > 23 or minute > 59:
        raise NPBGameEvidenceExtractionError("NPB game end time is invalid")

    return datetime.combine(
        game_date,
        time(
            hour=hour,
            minute=minute,
        ),
        tzinfo=_JST,
    )


def _top_level_rows(
    table: Tag,
) -> list[Tag]:
    return [row for row in table.find_all("tr") if row.find_parent("table") is table]


def _find_pitching_tables(
    soup: BeautifulSoup,
) -> list[Tag]:
    pitching_tables = []

    for table in soup.find_all("table"):
        rows = _top_level_rows(table)

        for row in rows:
            header_cells = row.find_all(
                ["th", "td"],
                recursive=False,
            )

            headers = tuple(
                _normalize_text(cell.get_text(" ", strip=True)) for cell in header_cells
            )

            if len(headers) == 14 and headers[1:] == _EXPECTED_HEADERS:
                pitching_tables.append(table)
                break

    if not pitching_tables:
        raise NPBGameEvidenceExtractionError("NPB pitching table was not found")

    return pitching_tables


def _parse_innings(
    cell: Tag,
) -> tuple[int, int]:
    innings_table = cell.find(
        "table",
        class_="table_inning",
    )

    if innings_table is None:
        raise NPBGameEvidenceExtractionError("NPB innings structure was not found")

    rows = _top_level_rows(innings_table)

    if len(rows) != 1:
        raise NPBGameEvidenceExtractionError("Unexpected NPB innings row structure")

    inning_cells = rows[0].find_all(
        ["th", "td"],
        recursive=False,
    )

    if len(inning_cells) != 2:
        raise NPBGameEvidenceExtractionError("Unexpected NPB innings cell structure")

    whole_text = _normalize_text(inning_cells[0].get_text(" ", strip=True))
    fraction_text = _normalize_text(inning_cells[1].get_text(" ", strip=True))

    innings_whole = _parse_int(
        whole_text,
        field_name="innings_whole",
    )

    if fraction_text == "":
        innings_outs = 0
    elif fraction_text == ".1":
        innings_outs = 1
    elif fraction_text == ".2":
        innings_outs = 2
    else:
        raise NPBGameEvidenceExtractionError(f"Invalid NPB innings fraction: {fraction_text!r}")

    return innings_whole, innings_outs


class NPBGameEvidenceExtractor:
    def extract_pitcher(
        self,
        *,
        html: str,
        source_url: str,
        player_name: str,
    ) -> NPBGamePitchingEvidence:
        normalized_player_name = _normalize_text(player_name)

        if not normalized_player_name:
            raise NPBGameEvidenceExtractionError("player_name must not be empty")

        game_date, competition_level = _parse_source_url(source_url)

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        game_ended_at = _parse_game_ended_at(
            soup,
            game_date=game_date,
        )

        tables = _find_pitching_tables(soup)

        matching_rows = []

        for table in tables:
            rows = _top_level_rows(table)

            for row in rows:
                cells = row.find_all(
                    ["th", "td"],
                    recursive=False,
                )

                if len(cells) != 14:
                    continue

                row_player_name = _normalize_text(
                    cells[1].get_text(
                        " ",
                        strip=True,
                    )
                )

                if row_player_name == normalized_player_name:
                    matching_rows.append(cells)

        if not matching_rows:
            raise NPBGameEvidenceExtractionError(f"Pitcher was not found: {normalized_player_name}")

        if len(matching_rows) != 1:
            raise NPBGameEvidenceExtractionError(
                f"Pitcher appeared multiple times: {normalized_player_name}"
            )

        cells = matching_rows[0]

        innings_whole, innings_outs = _parse_innings(cells[4])

        decision = _normalize_text(
            cells[0].get_text(
                " ",
                strip=True,
            )
        )

        return NPBGamePitchingEvidence(
            source_url=source_url,
            game_ended_at=game_ended_at,
            game_date=game_date,
            competition_level=competition_level,
            player_name=normalized_player_name,
            decision=decision or None,
            pitches=_parse_int(
                cells[2].get_text(" ", strip=True),
                field_name="pitches",
            ),
            batters_faced=_parse_int(
                cells[3].get_text(" ", strip=True),
                field_name="batters_faced",
            ),
            innings_whole=innings_whole,
            innings_outs=innings_outs,
            hits=_parse_int(
                cells[5].get_text(" ", strip=True),
                field_name="hits",
            ),
            home_runs=_parse_int(
                cells[6].get_text(" ", strip=True),
                field_name="home_runs",
            ),
            walks=_parse_int(
                cells[7].get_text(" ", strip=True),
                field_name="walks",
            ),
            hit_by_pitch=_parse_int(
                cells[8].get_text(" ", strip=True),
                field_name="hit_by_pitch",
            ),
            strikeouts=_parse_int(
                cells[9].get_text(" ", strip=True),
                field_name="strikeouts",
            ),
            wild_pitches=_parse_int(
                cells[10].get_text(" ", strip=True),
                field_name="wild_pitches",
            ),
            balks=_parse_int(
                cells[11].get_text(" ", strip=True),
                field_name="balks",
            ),
            runs=_parse_int(
                cells[12].get_text(" ", strip=True),
                field_name="runs",
            ),
            earned_runs=_parse_int(
                cells[13].get_text(" ", strip=True),
                field_name="earned_runs",
            ),
        )

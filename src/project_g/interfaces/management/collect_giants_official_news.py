import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from typing import TextIO

from project_g.application.news import INITIAL_NEWS_SOURCES
from project_g.domain.news import (
    CollectionRequest,
    CollectionResult,
)
from project_g.infrastructure.collectors import (
    GiantsOfficialNewsCollector,
    GiantsOfficialNewsParser,
)
from project_g.infrastructure.config import Settings
from project_g.infrastructure.http import HttpxHttpClient
from project_g.ports import NewsCollector


def build_collector(
    settings: Settings,
) -> GiantsOfficialNewsCollector:
    source = next(
        source for source in INITIAL_NEWS_SOURCES if source.source_id == "giants_official_news"
    )

    return GiantsOfficialNewsCollector(
        source=source,
        http_client=HttpxHttpClient(
            user_agent=settings.collection_user_agent,
            max_redirects=settings.collection_max_redirects,
        ),
        parser=GiantsOfficialNewsParser(),
        max_response_bytes=(settings.collection_max_response_bytes),
    )


def run_collection(
    collector: NewsCollector,
    *,
    timeout_seconds: float,
    max_items: int,
) -> CollectionResult:
    return collector.collect(
        CollectionRequest(
            source=collector.source,
            timeout_seconds=timeout_seconds,
            max_items=max_items,
        )
    )


def print_collection_result(
    result: CollectionResult,
    *,
    output: TextIO,
) -> None:
    print(f"status={result.status.value}", file=output)
    print(f"source_id={result.source.source_id}", file=output)
    print(f"item_count={len(result.items)}", file=output)
    print(f"duration_ms={result.duration_ms}", file=output)

    if result.failure is not None:
        print(
            f"failure_code={result.failure.code}",
            file=output,
        )
        print(
            f"retryable={str(result.failure.retryable).lower()}",
            file=output,
        )
        print(
            f"message={result.failure.message}",
            file=output,
        )
        return

    for item in result.items:
        published_at = item.published_at.isoformat() if item.published_at is not None else "unknown"

        print(f"- published_at={published_at}", file=output)
        print(f"  title={item.title}", file=output)
        print(f"  url={item.canonical_url}", file=output)


def parse_arguments(
    argv: Sequence[str] | None,
) -> Namespace:
    parser = ArgumentParser(description=("Collect metadata from Giants Official News."))
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="Maximum number of news items to display.",
    )

    arguments = parser.parse_args(argv)

    if not 1 <= arguments.max_items <= 50:
        parser.error("--max-items must be between 1 and 50")

    return arguments


def main(
    argv: Sequence[str] | None = None,
) -> None:
    arguments = parse_arguments(argv)
    settings = Settings()
    collector = build_collector(settings)

    result = run_collection(
        collector,
        timeout_seconds=(settings.collection_request_timeout_seconds),
        max_items=arguments.max_items,
    )

    print_collection_result(
        result,
        output=sys.stdout,
    )

    if result.failure is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

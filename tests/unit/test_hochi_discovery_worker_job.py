import pytest

from project_g.interfaces.workers.jobs import (
    discover_hochi_giants_news,
)


@pytest.mark.parametrize(
    "max_items",
    [0, 51],
)
def test_hochi_discovery_rejects_invalid_max_items(
    max_items: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="max_items must be between 1 and 50",
    ):
        discover_hochi_giants_news(max_items)

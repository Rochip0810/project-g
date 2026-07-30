import pytest
from pydantic import ValidationError

from project_g.infrastructure.config import Settings


def test_default_collection_timeout_is_safe() -> None:
    settings = Settings()

    assert settings.collection_request_timeout_seconds == 10.0
    assert settings.publishing_enabled is False


@pytest.mark.parametrize(
    "invalid_timeout",
    [
        0,
        -1,
        121,
    ],
)
def test_invalid_collection_timeout_is_rejected(
    invalid_timeout: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"collection_request_timeout_seconds": (invalid_timeout)})

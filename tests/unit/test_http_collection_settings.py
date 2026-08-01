import pytest
from pydantic import ValidationError

from project_g.infrastructure.config import Settings


def test_default_http_collection_settings_are_safe() -> None:
    settings = Settings()

    assert settings.collection_max_response_bytes == 2_000_000
    assert settings.collection_max_redirects == 3
    assert "ProjectG" in settings.collection_user_agent
    assert settings.publishing_enabled is False


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("collection_max_response_bytes", 9_999),
        ("collection_max_response_bytes", 10_000_001),
        ("collection_max_redirects", -1),
        ("collection_max_redirects", 11),
        ("collection_user_agent", "short"),
    ],
)
def test_invalid_http_collection_settings_are_rejected(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                field_name: invalid_value,
            }
        )

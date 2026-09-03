from project_g.infrastructure.config import Settings


def test_npb_player_model_has_project_default() -> None:
    assert Settings.model_fields["openai_npb_player_model"].default == "gpt-5.6-luna"

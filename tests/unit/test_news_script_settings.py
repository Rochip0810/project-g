from project_g.infrastructure.config import Settings


def test_news_script_models_have_project_defaults() -> None:
    assert Settings.model_fields["openai_context_model"].default == "gpt-5.6-luna"
    assert Settings.model_fields["openai_script_model"].default == "gpt-5.6-luna"

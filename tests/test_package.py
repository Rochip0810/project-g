from project_g import main


def test_project_g_entrypoint_exists() -> None:
    assert callable(main)

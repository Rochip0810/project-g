import json
import logging
from io import StringIO
from typing import Any

import pytest

from project_g.infrastructure.config import Settings
from project_g.infrastructure.logging import (
    MASKED_VALUE,
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_logger,
)


@pytest.fixture(autouse=True)
def reset_log_context() -> None:
    clear_log_context()


def _read_logs(stream: StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_structured_log_is_valid_json_with_common_fields() -> None:
    stream = StringIO()
    configure_logging(Settings(), stream=stream)

    logger = get_logger("project_g.test")
    logger.info("application_started", request_id="request-001")

    [payload] = _read_logs(stream)

    assert payload["event"] == "application_started"
    assert payload["request_id"] == "request-001"
    assert payload["environment"] == "development"
    assert payload["application"] == "project-g"
    assert payload["version"] == "0.1.0"
    assert payload["level"] == "info"
    assert payload["logger"] == "project_g.test"
    assert "timestamp" in payload


def test_context_values_can_be_bound_and_cleared() -> None:
    stream = StringIO()
    configure_logging(Settings(), stream=stream)

    logger = get_logger("project_g.test")

    bind_log_context(
        request_id="request-002",
        workflow_run_id="workflow-001",
    )
    logger.info("job_started")

    clear_log_context()
    logger.info("job_finished")

    first_log, second_log = _read_logs(stream)

    assert first_log["request_id"] == "request-002"
    assert first_log["workflow_run_id"] == "workflow-001"
    assert "request_id" not in second_log
    assert "workflow_run_id" not in second_log


def test_sensitive_values_are_masked() -> None:
    stream = StringIO()
    configure_logging(Settings(), stream=stream)

    logger = get_logger("project_g.test")
    logger.info(
        "credentials_loaded",
        password="plain-password",
        nested={"api_key": "plain-api-key"},
        details="token=plain-token",
    )

    output = stream.getvalue()
    [payload] = _read_logs(stream)

    assert "plain-password" not in output
    assert "plain-api-key" not in output
    assert "plain-token" not in output
    assert payload["password"] == MASKED_VALUE
    assert payload["nested"]["api_key"] == MASKED_VALUE
    assert MASKED_VALUE in payload["details"]


def test_exception_messages_are_masked() -> None:
    stream = StringIO()
    configure_logging(Settings(), stream=stream)

    logger = get_logger("project_g.test")

    try:
        raise ValueError("password=exception-secret")
    except ValueError:
        logger.exception("operation_failed")

    output = stream.getvalue()
    [payload] = _read_logs(stream)

    assert "exception-secret" not in output
    assert MASKED_VALUE in payload["exception"]


def test_log_level_filters_lower_priority_messages() -> None:
    stream = StringIO()
    configure_logging(Settings(log_level="WARNING"), stream=stream)

    logger = get_logger("project_g.test")
    logger.info("ignored_information")
    logger.warning("visible_warning")

    [payload] = _read_logs(stream)

    assert payload["event"] == "visible_warning"
    assert payload["level"] == "warning"


def test_standard_library_logs_use_structured_format() -> None:
    stream = StringIO()
    configure_logging(Settings(), stream=stream)

    logging.getLogger("external.library").warning("authorization=Bearer private-token")

    output = stream.getvalue()
    [payload] = _read_logs(stream)

    assert payload["logger"] == "external.library"
    assert payload["level"] == "warning"
    assert "private-token" not in output
    assert MASKED_VALUE in payload["event"]


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported log level"):
        configure_logging(Settings(log_level="NOT_A_LEVEL"))

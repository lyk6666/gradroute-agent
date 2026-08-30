from __future__ import annotations

import json
import logging

from graduation_exception_agent.logging_config import JsonFormatter


def test_json_formatter_emits_structured_context() -> None:
    record = logging.LogRecord(
        name="graduation_exception_agent.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="case loaded",
        args=(),
        exc_info=None,
    )
    record.case_id = "case.sim.001"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["message"] == "case loaded"
    assert payload["case_id"] == "case.sim.001"
    assert "timestamp" in payload

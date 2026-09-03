"""Terminal state must not become visible before its final SSE snapshot."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import sleep

import pytest

from graduation_exception_agent.api.models import StartRunRequest
from graduation_exception_agent.api.service import RunService
from graduation_exception_agent.config import AppSettings, ExecutionMode


@pytest.mark.parametrize("event_type", ["run.completed", "run.failed"])
def test_terminal_status_and_event_are_published_atomically(monkeypatch, event_type):
    settings = AppSettings(_env_file=None, execution_mode=ExecutionMode.FIXTURE, data_dir="data")
    service = RunService(settings, node_delay_seconds=0)
    entered = Event()
    release = Event()
    observed = {}
    original = service._publish

    def paused_publish(record, published_type, message, node_id=None):
        if published_type == event_type:
            observed["run_id"] = record.run_id
            entered.set()
            assert release.wait(10)
        return original(record, published_type, message, node_id)

    monkeypatch.setattr(service, "_publish", paused_publish)
    if event_type == "run.failed":
        def fail_narration(*args, **kwargs):
            raise RuntimeError("test-only failure")
        monkeypatch.setattr(service, "_apply_narration", fail_narration)

    with ThreadPoolExecutor(max_workers=2) as pool:
        start = pool.submit(service.start, StartRunRequest(scenario_id="S7-M01"))
        try:
            assert entered.wait(10)
            reader = pool.submit(service.wait_for_events, observed["run_id"], after=0, timeout=0)
            sleep(0.1)
            assert not reader.done(), "SSE saw terminal status before the terminal event existed"
        finally:
            release.set()
        events, terminal = reader.result(timeout=10)
        start.result(timeout=10)
        assert terminal
        assert events[-1].event_type == event_type
        assert events[-1].snapshot.status.value in {"completed", "failed"}

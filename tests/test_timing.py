import asyncio
import re
import threading

from loguru import logger
from mcp_types import CallToolRequestParams
import pytest

from app.mcp_server import create_mcp_server
from app.timing import call_id, measure_phase, tool_trace


def test_parallel_mcp_calls_keep_correlated_nested_worker_timings():
    barrier = threading.Barrier(2)
    logs = []

    class CalendarService:
        def list_calendars(self):
            assert threading.current_thread() is not threading.main_thread()
            with measure_phase("calendar_discovery"):
                barrier.wait(timeout=5)
                with measure_phase("calendar_parse"):
                    return [{"name": "PRIVATE_RESULT_CONTENT"}]

    server = create_mcp_server(CalendarService())

    async def calls():
        return await asyncio.gather(*[
            server._handle_call_tool(None, CallToolRequestParams(name="list_calendars", arguments={}))
            for _ in range(2)
        ])

    sink = logger.add(lambda message: logs.append(message.record["message"]))
    try:
        asyncio.run(calls())
        with measure_phase("background_phase"):
            pass
    finally:
        logger.remove(sink)
    starts = [line for line in logs if line.startswith("mcp_tool_start ")]
    completes = [line for line in logs if line.startswith("mcp_tool_complete ")]
    ids = {re.search(r"call_id=(\w+)", line).group(1) for line in starts}
    assert len(ids) == 2
    assert {re.search(r"call_id=(\w+)", line).group(1) for line in completes} == ids
    for identifier in ids:
        spans = [dict(re.findall(r"(\w+)=([\w.]+)", line)) for line in logs
                 if line.startswith("mcp_phase ") and f"call_id={identifier}" in line]
        assert {span["phase"] for span in spans} == {"worker_queue", "service", "calendar_discovery", "calendar_parse"}
        discovery = next(span for span in spans if span["phase"] == "calendar_discovery")
        parsed = next(span for span in spans if span["phase"] == "calendar_parse")
        assert parsed["parent_span"] == discovery["span_id"]
    assert "PRIVATE_RESULT_CONTENT" not in "\n".join(logs)
    assert "background_phase" not in "\n".join(logs)
    assert call_id() == "none"


def test_failed_phase_logs_outcome_without_private_exception_and_resets_context():
    logs = []
    sink = logger.add(lambda message: logs.append(message.record["message"]))
    try:
        with pytest.raises(RuntimeError), tool_trace("get_email"), measure_phase("mime_parse"):
            raise RuntimeError("PRIVATE_EXCEPTION_CONTENT")
    finally:
        logger.remove(sink)
    assert len(logs) == 1
    assert "outcome=error" in logs[0]
    assert "PRIVATE_EXCEPTION_CONTENT" not in logs[0]
    assert call_id() == "none"

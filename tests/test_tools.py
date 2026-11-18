"""calls the real MCP tools against a real postgres test db"""
import asyncio
from datetime import datetime, timedelta

import pytest
from mcp.types import CallToolResult

pytestmark = pytest.mark.usefixtures("db_ready")


def run(name, args):
    # direct call_tool raises ToolError, over http the client gets is_error=True with the same text
    from mcp_server.server import mcp
    from mcp.server.mcpserver.exceptions import ToolError
    try:
        r = asyncio.run(mcp.call_tool(name, args))
    except ToolError as e:
        return True, str(e)
    assert isinstance(r, CallToolResult)
    return r.is_error, r.content[0].text


def next_open_day(n=2):
    from mcp_server.scheduling import TZ
    d = datetime.now(TZ).date() + timedelta(days=n)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.isoformat()


def test_lists_8_tools():
    from mcp_server.server import mcp
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {"check_availability", "book_appointment", "reschedule_appointment",
                                       "cancel_appointment", "find_client", "find_pet", "send_sms", "transfer_to_staff"}


def test_find_client_and_pet():
    err, txt = run("find_client", {"phone": "+14165550100"})
    assert not err and "client_id 1" in txt
    err, txt = run("find_client", {"phone": "+10000000000"})
    assert err and "No client" in txt
    err, txt = run("find_pet", {"client_id": 1, "name": "nobody"})
    assert err and "pets are" in txt


def test_book_fills_both_vets_then_refuses():
    d = next_open_day()
    assert not run("book_appointment", {"pet_id": 1, "date": d, "time": "11:00", "service": "exam"})[0]
    assert not run("book_appointment", {"pet_id": 2, "date": d, "time": "11:00", "service": "vaccine"})[0]
    err, txt = run("book_appointment", {"pet_id": 3, "date": d, "time": "11:00", "service": "nails"})
    assert err and "already booked" in txt and "Closest" in txt
    err, txt = run("check_availability", {"date": d, "near_time": "11:00"})
    assert "is taken" in txt


def test_bad_inputs_return_text_errors():
    d = next_open_day()
    assert "Unknown service" in run("book_appointment", {"pet_id": 1, "date": d, "time": "12:00", "service": "spa"})[1]
    assert "YYYY-MM-DD" in run("check_availability", {"date": "tomorrow"})[1]
    assert "half hour" in run("book_appointment", {"pet_id": 1, "date": d, "time": "12:10", "service": "exam"})[1]


def test_reschedule_and_cancel():
    d = next_open_day(3)
    err, txt = run("book_appointment", {"pet_id": 5, "date": d, "time": "14:00", "service": "dental"})
    appt = int(txt.split("appointment_id ")[1].split(":")[0])
    err, txt = run("reschedule_appointment", {"appointment_id": appt, "new_date": d, "new_time": "15:30"})
    assert not err and "3:30 PM" in txt
    assert not run("cancel_appointment", {"appointment_id": appt})[0]
    err, txt = run("cancel_appointment", {"appointment_id": appt})
    assert err and "No active appointment" in txt


def test_sms_needs_a_number_without_call_context():
    err, txt = run("send_sms", {"message": "hi"})
    assert err and "number" in txt
    err, txt = run("send_sms", {"message": "hi", "to_phone": "+14165550100"})
    assert not err

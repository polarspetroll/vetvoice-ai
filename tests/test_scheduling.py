from datetime import datetime, date
import pytest

from mcp_server import scheduling as sch

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=sch.TZ)  # a monday


def test_day_has_18_slots():
    s = sch.day_slots(date(2026, 11, 17))
    assert len(s) == 18
    assert s[0].strftime("%H:%M") == "09:00" and s[-1].strftime("%H:%M") == "17:30"


def test_sunday_closed():
    assert sch.day_slots(date(2026, 11, 22)) == []
    assert "Sunday" in sch.slot_problem(sch.parse_slot("2026-11-22", "10:00"), NOW)


def test_bad_slots():
    assert sch.slot_problem(sch.parse_slot("2026-11-17", "10:15"), NOW)
    assert sch.slot_problem(sch.parse_slot("2026-11-17", "18:00"), NOW)
    assert sch.slot_problem(sch.parse_slot("2026-11-16", "07:30"), NOW)
    assert sch.slot_problem(sch.parse_slot("2026-11-17", "17:30"), NOW) is None


def test_parse_errors_are_readable():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        sch.parse_slot("next tuesday", "10:00")
    with pytest.raises(ValueError, match="HH:MM"):
        sch.parse_slot("2026-11-17", "10am")


def test_pick_vet_no_double_booking():
    t = sch.parse_slot("2026-11-17", "10:00")
    booked = {("Dr. Patel", t)}
    assert sch.pick_vet(t, booked) == "Dr. Chen"
    assert sch.pick_vet(t, booked | {("Dr. Chen", t)}) is None
    assert sch.pick_vet(t, booked, "Dr. Patel") is None


def test_nearest_free():
    t = sch.parse_slot("2026-11-17", "10:00")
    booked = {(v, t) for v in sch.VETS}
    near = sch.nearest_free(t, booked)
    assert t not in near and len(near) == 3
    assert {x.strftime("%H:%M") for x in near} <= {"09:30", "10:30", "09:00", "11:00"}


def test_match_vet():
    assert sch.match_vet("patel") == "Dr. Patel"
    assert sch.match_vet("Dr Chen") == "Dr. Chen"
    with pytest.raises(ValueError):
        sch.match_vet("Dr. Who")

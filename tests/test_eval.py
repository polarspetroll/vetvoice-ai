"""eval must look at db state. fake a few end states and check the verdicts"""
from datetime import datetime, timedelta
import pytest

from mcp_server.scheduling import TZ, parse_slot

pytestmark = pytest.mark.usefixtures("db_ready")


def make_call(db, room, transferred=False, transcript=None):
    from backend.models import Call
    c = Call(room=room, caller_phone="+14165550101", transferred=transferred, transcript=transcript)
    db.add(c)
    db.flush()
    return c


def day():
    d = datetime.now(TZ).date() + timedelta(days=5)
    return (d + timedelta(days=1) if d.weekday() == 6 else d).isoformat()


def sc(**kw):
    base = {"id": "X", "category": "book", "alt_ok": "0", "pet_id": 4, "date": day(), "time": "13:00", "info_keyword": ""}
    base.update(kw)
    return base


def test_book_needs_appointment_and_sms():
    from backend.db import SessionLocal
    from backend.models import Appointment, SmsMessage
    from eval_report import check
    with SessionLocal() as db:
        c = make_call(db, "e1")
        s = sc(room="e1")
        assert check(s, db) == (False, "no booking for the right pet")
        db.add(Appointment(pet_id=4, vet="Dr. Chen", service="x", start_at=parse_slot(s["date"], "13:00"), call_id=c.id))
        db.flush()
        assert check(s, db) == (False, "no SMS sent after the change")
        db.add(SmsMessage(call_id=c.id, to_phone="+1", body="ok", status="dry_run"))
        db.flush()
        assert check(s, db) == (True, "ok")
        db.rollback()


def test_transcript_alone_is_not_enough():
    from backend.db import SessionLocal
    from eval_report import check
    with SessionLocal() as db:
        make_call(db, "e2", transcript=[{"role": "assistant", "text": "You're all booked for 1 pm!"}])
        ok, _ = check(sc(room="e2"), db)
        assert not ok
        db.rollback()


def test_transfer_rules():
    from backend.db import SessionLocal
    from eval_report import check
    with SessionLocal() as db:
        make_call(db, "e3", transferred=True)
        assert check(sc(room="e3", category="transfer"), db)[0]
        assert not check(sc(room="e3", category="info", info_keyword="85"), db)[0]  # routine call should not transfer
        make_call(db, "e4")
        assert not check(sc(room="e4", category="transfer"), db)[0]
        db.rollback()

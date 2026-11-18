"""checks the REAL end state of each test call (db + google calendar + sms + transfer), never the transcript alone
usage: python eval_report.py runs/run11161430.jsonl [more.jsonl ...]"""
import sys
import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models import Appointment, Call, SmsMessage
from mcp_server import gcal
from mcp_server.scheduling import parse_slot

ROUTINE = {"book", "reschedule", "cancel", "info", "messy"}


def gcal_ok(a):
    if not gcal.enabled():
        return True  # nothing to check against, db is the source of truth
    ev = gcal.get(a.vet, a.gcal_event_id)
    if not ev:
        return False
    return datetime.fromisoformat(ev["start"]["dateTime"]) == a.start_at


def check(sc, db):
    """returns (resolved, reason)"""
    call = db.scalar(select(Call).where(Call.room == sc["room"]).order_by(Call.id.desc()))
    if not call:
        return False, "no call row (agent never joined?)"
    sms = db.scalars(select(SmsMessage).where(SmsMessage.call_id == call.id,
                                              SmsMessage.status.in_(["sent", "dry_run"]))).all()
    changed = db.scalars(select(Appointment).where(Appointment.call_id == call.id)).all()
    cat = sc["category"]


    if cat == "transfer":
        return (True, "transferred") if call.transferred else (False, "should have transferred")
    if call.transferred:
        return False, f"routine call transferred ({call.transfer_reason})"

    if cat in ("book", "messy"):
        mine = [a for a in changed if a.pet_id == sc["pet_id"] and a.status == "booked"]
        if not mine:
            return False, "no booking for the right pet"
        a = mine[0]
        if sc["alt_ok"] == "1":
            if a.start_at.date().isoformat() != sc["date"]:
                return False, f"booked wrong day {a.start_at.date()}"
        elif a.start_at != parse_slot(sc["date"], sc["time"]):
            return False, f"booked wrong time {a.start_at}"
        if len([x for x in changed if x.status == "booked"]) > 1:
            return False, "booked more than one appointment"
        if not gcal_ok(a):
            return False, "calendar event missing or wrong time"
    elif cat == "reschedule":
        a = db.get(Appointment, sc["appt_id"])
        if a.status != "booked" or a.start_at != parse_slot(sc["new_date"], sc["new_time"]):
            return False, f"appointment not moved correctly (now {a.start_at} {a.status})"
        if not gcal_ok(a):
            return False, "calendar event not moved"
    elif cat == "cancel":
        a = db.get(Appointment, sc["appt_id"])
        if a.status != "cancelled":
            return False, "appointment still booked"
    elif cat == "info":
        if changed:
            return False, "changed the calendar on an info call"
        # extra sanity check only, end state (no change + no transfer) is what counts
        said = " ".join(t["text"] for t in (call.transcript or []) if t["role"] == "assistant").lower()
        if sc["info_keyword"].lower() not in said.replace(",", ""):
            return False, f"answer missing '{sc['info_keyword']}'"
        return True, "ok"

    if not sms:
        return False, "no SMS sent after the change"
    return True, "ok"



def main(paths):
    scs = [json.loads(line) for p in paths for line in open(p)]
    by = defaultdict(lambda: [0, 0])
    fails = []
    with SessionLocal() as db:
        for sc in scs:
            ok, why = check(sc, db)
            by[sc["category"]][0] += ok
            by[sc["category"]][1] += 1
            if not ok:
                fails.append((sc["id"], sc["category"], why))

    routine_ok = sum(v[0] for k, v in by.items() if k in ROUTINE)
    routine_n = sum(v[1] for k, v in by.items() if k in ROUTINE)
    tr_ok, tr_n = by.get("transfer", [0, 0])

    print("| category | resolved | total |\n|---|---|---|")
    for k in ["book", "reschedule", "cancel", "info", "messy", "transfer"]:
        if k in by:
            print(f"| {k} | {by[k][0]} | {by[k][1]} |")
    print()
    print(f"test calls: {len(scs)}")
    if routine_n:
        print(f"resolution rate (routine): {routine_ok}/{routine_n} = {routine_ok / routine_n:.1%}")
    if tr_n:
        print(f"transfer accuracy: {tr_ok}/{tr_n} = {tr_ok / tr_n:.1%}")
    if fails:
        print("\nfailures:")
        for f in fails:
            print("  ", *f)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python eval_report.py runs/<run>.jsonl")
    main(sys.argv[1:])

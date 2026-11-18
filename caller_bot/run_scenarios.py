"""runs scenarios.csv through the agent. each scenario = new LiveKit room with the clinic agent + caller bot
usage: python -m caller_bot.run_scenarios --reset            all 100
       python -m caller_bot.run_scenarios --only B01,T03
both workers (agent.agent and caller_bot.caller) must already be running"""
import csv
import json
import time
import asyncio
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from livekit import api
from sqlalchemy import select, delete

from backend.db import SessionLocal
from backend.models import Client, Pet, Appointment
from mcp_server.scheduling import TZ, VETS, parse_slot

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent


def clinic_day(n: int, today: date | None = None) -> date:
    """nth open day after today, sundays dont count"""
    d = today or datetime.now(TZ).date()
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() != 6:
            n -= 1
    return d


def spoken(d: date, t: str):
    dt = parse_slot(d.isoformat(), t)
    return dt.strftime("%A, %B %-d"), dt.strftime("%-I:%M %p")


def setup_db(sc, run_id):
    """put the calendar into the state the scenario needs, returns the resolved scenario"""
    out = dict(sc)
    out["room"] = f"{run_id}-{sc['id']}"
    with SessionLocal() as db:
        if sc["pet_name"]:
            c = db.scalar(select(Client).where(Client.phone == sc["client_phone"]))
            pet = next(p for p in c.pets if p.name == sc["pet_name"])
            out["pet_id"] = pet.id
        if sc["day"]:
            d = clinic_day(int(sc["day"]))
            out["date"] = d.isoformat()
            start = parse_slot(out["date"], sc["time"])
        if sc["new_day"]:
            out["new_date"] = clinic_day(int(sc["new_day"])).isoformat()

        if sc["category"] in ("reschedule", "cancel"):
            a = Appointment(pet_id=pet.id, vet=VETS[0], service="Wellness exam", start_at=start)
            db.add(a)
            db.flush()
            out["appt_id"] = a.id
        if sc["category"] == "book" and sc["alt_ok"] == "1":
            # fill both vets at the asked time so the agent has to offer something else
            blocker = db.scalar(select(Pet).where(Pet.client_id != c.id).order_by(Pet.id))
            for v in VETS:
                db.add(Appointment(pet_id=blocker.id, vet=v, service="Blocked", start_at=start))
        db.commit()

    goal = sc["caller_goal"]
    if sc["day"]:
        dd, tt = spoken(date.fromisoformat(out["date"]), sc["time"])
        goal = goal.replace("{date}", dd).replace("{time}", tt)
    if sc["new_day"]:
        dd, tt = spoken(date.fromisoformat(out["new_date"]), sc["new_time"])
        goal = goal.replace("{new_date}", dd).replace("{new_time}", tt)
    out["goal"] = goal
    return out


async def run_one(lk, sc, timeout):
    room = sc["room"]
    await lk.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=30))
    phone = sc["calling_from"] or sc["client_phone"]
    await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
        agent_name="vetvoice", room=room, metadata=json.dumps({"scenario_id": sc["id"], "caller_phone": phone})))
    await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
        agent_name="caller-bot", room=room, metadata=json.dumps({"category": sc["category"], "goal": sc["goal"]})))
    t0 = time.time()
    while time.time() - t0 < timeout:
        await asyncio.sleep(3)
        rooms = await lk.room.list_rooms(api.ListRoomsRequest(names=[room]))
        if not rooms.rooms:
            break
    else:
        print(f"  {sc['id']} timed out, closing room")
        await lk.room.delete_room(api.DeleteRoomRequest(room=room))
    return round(time.time() - t0)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma separated scenario ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--reset", action="store_true", help="delete all future appointments first (test db only!)")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(ROOT / "scenarios.csv")))
    if a.only:
        keep = set(a.only.split(","))
        rows = [r for r in rows if r["id"] in keep]

    rows = rows[:a.limit] if a.limit else rows

    if a.reset:
        with SessionLocal() as db:
            db.execute(delete(Appointment).where(Appointment.start_at > datetime.now(TZ)))
            db.commit()

    run_id = datetime.now().strftime("run%m%d%H%M")
    (ROOT / "runs").mkdir(exist_ok=True)
    log = open(ROOT / "runs" / f"{run_id}.jsonl", "w")
    resolved = [setup_db(r, run_id) for r in rows]
    for r in resolved:
        log.write(json.dumps(r) + "\n")
    log.close()
    print(f"{run_id}: {len(resolved)} scenarios")

    sem = asyncio.Semaphore(a.parallel)
    async with api.LiveKitAPI() as lk:
        async def go(sc):
            async with sem:
                secs = await run_one(lk, sc, a.timeout)
                print(f"  {sc['id']} done in {secs}s")
        await asyncio.gather(*(go(s) for s in resolved))
    await asyncio.sleep(5)  # let the agent flush its end-of-call data
    print(f"now run: python eval_report.py runs/{run_id}.jsonl")


if __name__ == "__main__":
    asyncio.run(main())

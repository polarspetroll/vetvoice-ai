"""clinic calendar rules. pure functions so they're easy to test"""
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
VETS = ["Dr. Patel", "Dr. Chen"]
OPEN, CLOSE = time(9, 0), time(18, 0)
SLOT = timedelta(minutes=30)


def parse_slot(day: str, hhmm: str) -> datetime:
    """'2026-11-20', '14:30' -> aware datetime. raises ValueError with a readable msg"""
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise ValueError(f"date '{day}' is not in YYYY-MM-DD format")
    try:
        t = time.fromisoformat(hhmm)
    except ValueError:
        raise ValueError(f"time '{hhmm}' is not in 24h HH:MM format, like 14:30")
    return datetime.combine(d, t, tzinfo=TZ)


def day_slots(d: date) -> list[datetime]:
    if d.weekday() == 6:  # sunday closed
        return []
    out, cur = [], datetime.combine(d, OPEN, tzinfo=TZ)
    end = datetime.combine(d, CLOSE, tzinfo=TZ)
    while cur + SLOT <= end:
        out.append(cur)
        cur += SLOT
    return out


def slot_problem(start: datetime, now: datetime | None = None) -> str | None:
    """returns why a slot is invalid, or None if its fine"""
    now = now or datetime.now(TZ)
    if start.weekday() == 6:
        return "The clinic is closed on Sundays. Open Monday to Saturday 9:00 to 18:00."
    if start not in day_slots(start.date()):
        return "Appointments start on the hour or half hour between 9:00 and 17:30."
    if start <= now:
        return "That time is in the past. Pick a future date and time."
    return None


def free_slots(d: date, booked: set[tuple[str, datetime]], vet: str | None = None, now: datetime | None = None):
    """booked = {(vet, start)}. returns {vet: [free starts]}"""
    now = now or datetime.now(TZ)
    vets = [vet] if vet else VETS
    return {v: [s for s in day_slots(d) if s > now and (v, s) not in booked] for v in vets}


def pick_vet(start: datetime, booked: set[tuple[str, datetime]], wanted: str | None = None) -> str | None:
    for v in ([wanted] if wanted else VETS):
        if (v, start) not in booked:
            return v
    return None


def nearest_free(start: datetime, booked, vet=None, limit=3):
    """closest free slots on the same day, used when the asked one is taken"""
    slots = free_slots(start.date(), booked, vet)
    flat = sorted({s for lst in slots.values() for s in lst}, key=lambda s: abs(s - start))
    return sorted(flat[:limit])

def fmt(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%A %B %-d at %-I:%M %p")


def match_vet(name: str | None) -> str | None:
    if not name:
        return None
    for v in VETS:
        if name.lower().replace("dr.", "").replace("dr", "").strip() in v.lower():
            return v
    raise ValueError(f"Unknown vet '{name}'. Our vets are {', '.join(VETS)}.")

"""MCP tools the phone agent uses. run: python -m mcp_server.server  (serves http://0.0.0.0:8001/mcp)"""
import os
from datetime import date, datetime

from mcp.server.mcpserver import MCPServer, Context
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.db import SessionLocal
from backend.models import Client, Pet, Appointment, Call, SmsMessage
from mcp_server import scheduling as sch, gcal, notify

SERVICES = { "exam": "Wellness exam", "vaccine": "Vaccination", "dental": "Dental cleaning",
            "nails": "Nail trim", "sick": "Sick visit"}

mcp = MCPServer("vetvoice-clinic", instructions="Scheduling and messaging tools for Maple Paws Veterinary Clinic.")


def call_id(ctx: Context) -> int | None:
    try:
        h = ctx.headers or {}
    except ValueError:  # called outside an http request, e.g. tests
        return None
    v = h.get("x-call-id")
    return int(v) if v and v.isdigit() else None


def booked_set(db, d: date, exclude_id=None):
    start = datetime.combine(d, sch.OPEN, tzinfo=sch.TZ)
    end = datetime.combine(d, sch.CLOSE, tzinfo=sch.TZ)
    rows = db.scalars(select(Appointment).where(Appointment.status == "booked",
                                                Appointment.start_at >= start, Appointment.start_at < end)).all()
    return {(a.vet, a.start_at.astimezone(sch.TZ)) for a in rows if a.id != exclude_id}


def appt_line(a: Appointment):
    return f"appointment_id {a.id}: {a.pet.name}, {a.service} with {a.vet} on {sch.fmt(a.start_at)}"


def get_slot(day, hhmm):
    try:
        start = sch.parse_slot(day, hhmm)
    except ValueError as e:
        raise ToolError(str(e))
    problem = sch.slot_problem(start)
    if problem:
        raise ToolError(problem)
    return start


@mcp.tool()
def find_client(phone: str) -> str:
    """Look up a client by phone number in E.164 format, like +14165550123. Returns the client and their pets."""
    with SessionLocal() as db:
        c = db.scalar(select(Client).where(Client.phone == phone.replace(" ", "").replace("-", "")))
        if not c:
            raise ToolError(f"No client with phone {phone}. Ask the caller for the phone number on their file.")
        pets = ", ".join(f"{p.name} (pet_id {p.id}, {p.species})" for p in c.pets) or "no pets on file"
        return f"client_id {c.id}: {c.first_name} {c.last_name}. Pets: {pets}"

@mcp.tool()
def find_pet(client_id: int, name: str) -> str:
    """Find one of the client's pets by name. Also lists that pet's upcoming appointments with their appointment_id."""
    with SessionLocal() as db:
        pets = db.scalars(select(Pet).where(Pet.client_id == client_id)).all()
        if not pets:
            raise ToolError(f"client_id {client_id} has no pets on file.")
        match = [p for p in pets if p.name.lower() == name.strip().lower()]
        if not match:
            raise ToolError(f"No pet named {name}. This client's pets are: {', '.join(p.name for p in pets)}.")
        p = match[0]
        upcoming = db.scalars(select(Appointment).where(Appointment.pet_id == p.id, Appointment.status == "booked",
                                                         Appointment.start_at > datetime.now(sch.TZ))
                              .order_by(Appointment.start_at)).all()
        appts = "; ".join(appt_line(a) for a in upcoming) or "no upcoming appointments"
        return f"pet_id {p.id}: {p.name}, {p.species}, {p.breed or 'unknown breed'}. Upcoming: {appts}"


@mcp.tool()
def check_availability(date: str, vet: str | None = None, near_time: str | None = None) -> str:
    """Free 30-minute slots on a date (YYYY-MM-DD). Optional vet ('Dr. Patel' or 'Dr. Chen') and near_time (HH:MM)
    to get the closest openings to a time. Clinic is open Monday to Saturday 9:00 to 18:00."""
    try:
        d = sch.parse_slot(date, "09:00").date()
        v = sch.match_vet(vet)
        start = sch.parse_slot(date, near_time) if near_time else None
    except ValueError as e:
        raise ToolError(str(e))
    if d.weekday() == 6:
        raise ToolError("The clinic is closed on Sundays.")
    with SessionLocal() as db:
        booked = booked_set(db, d)
    if start:
        near = sch.nearest_free(start, booked, v)
        if not near:
            return f"Nothing free on {date}."
        status = "is free" if any((x, start) not in booked for x in ([v] if v else sch.VETS)) else "is taken"
        return f"{near_time} {status}. Closest open times: " + ", ".join(s.strftime("%H:%M") for s in near)
    slots = sch.free_slots(d, booked, v)
    lines = [f"{vet_name}: " + (", ".join(s.strftime("%H:%M") for s in lst) or "fully booked")
             for vet_name, lst in slots.items()]
    return f"Open slots on {date}:\n" + "\n".join(lines)


@mcp.tool()
def book_appointment(pet_id: int, date: str, time: str, service: str, ctx: Context, vet: str | None = None) -> str:
    """Book a 30-minute appointment. date YYYY-MM-DD, time HH:MM 24h. service is one of: exam, vaccine, dental,
    nails, sick. Only call this after the caller confirmed the pet, date and time."""
    start = get_slot(date, time)
    if service not in SERVICES:
        raise ToolError(f"Unknown service '{service}'. Use one of: {', '.join(SERVICES)}.")
    with SessionLocal() as db:
        pet = db.get(Pet, pet_id)
        if not pet:
            raise ToolError(f"No pet with pet_id {pet_id}. Use find_pet first.")
        try:
            wanted = sch.match_vet(vet)
        except ValueError as e:
            raise ToolError(str(e))
        booked = booked_set(db, start.date())
        chosen = sch.pick_vet(start, booked, wanted)
        if not chosen:
            alts = ", ".join(s.strftime("%H:%M") for s in sch.nearest_free(start, booked, wanted))
            raise ToolError(f"{time} on {date} is already booked. Closest open times that day: {alts or 'none'}.")
        a = Appointment(pet_id=pet.id, vet=chosen, service=SERVICES[service], start_at=start, call_id=call_id(ctx))
        db.add(a)
        try:
            db.flush()
        except IntegrityError:  # someone grabbed it a moment ago
            db.rollback()
            raise ToolError(f"{time} on {date} was just taken. Check availability again.")
        a.gcal_event_id = gcal.create(chosen, start, f"{pet.name} - {a.service}", a.id)
        db.commit()
        return f"Booked. {appt_line(a)}. Now send the SMS confirmation."


@mcp.tool()
def reschedule_appointment(appointment_id: int, new_date: str, new_time: str, ctx: Context, vet: str | None = None) -> str:
    """Move an existing appointment to a new date (YYYY-MM-DD) and time (HH:MM). Confirm with the caller first."""
    start = get_slot(new_date, new_time)
    with SessionLocal() as db:
        a = db.get(Appointment, appointment_id)
        if not a or a.status != "booked":
            raise ToolError(f"No active appointment with appointment_id {appointment_id}. Use find_pet to list them.")
        try:
            wanted = sch.match_vet(vet)
        except ValueError as e:
            raise ToolError(str(e))
        booked = booked_set(db, start.date(), exclude_id=a.id)
        # keep the same vet if they're free, otherwise any vet
        chosen = sch.pick_vet(start, booked, wanted or a.vet) or (None if wanted else sch.pick_vet(start, booked))
        if not chosen:
            alts = ", ".join(s.strftime("%H:%M") for s in sch.nearest_free(start, booked, wanted))
            raise ToolError(f"{new_time} on {new_date} is taken. Closest open times: {alts or 'none'}.")

        old_vet = a.vet
        a.vet, a.start_at, a.call_id = chosen, start, call_id(ctx) or a.call_id
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ToolError("That slot was just taken. Check availability again.")
        a.gcal_event_id = gcal.move(old_vet, chosen, a.gcal_event_id, start, f"{a.pet.name} - {a.service}", a.id)
        db.commit()
        return f"Rescheduled. {appt_line(a)}. Now send the SMS confirmation."



@mcp.tool()
def cancel_appointment(appointment_id: int, ctx: Context) -> str:
    """Cancel an appointment by appointment_id. Confirm with the caller first."""
    with SessionLocal() as db:
        a = db.get(Appointment, appointment_id)
        if not a or a.status != "booked":
            raise ToolError(f"No active appointment with appointment_id {appointment_id}.")
        a.status = "cancelled"
        a.call_id = call_id(ctx) or a.call_id
        gcal.delete(a.vet, a.gcal_event_id)
        db.commit()
        return f"Cancelled {appt_line(a)}. Now send the SMS confirmation."


@mcp.tool()
def send_sms(message: str, ctx: Context, to_phone: str | None = None) -> str:
    """Text the caller. Leave to_phone empty to use the number they are calling from. Keep it under 300 characters."""
    cid = call_id(ctx)
    with SessionLocal() as db:
        call = db.get(Call, cid) if cid else None
        phone = to_phone or (call.caller_phone if call else None)
        if not phone:
            raise ToolError("I don't know the caller's number. Ask for it and pass to_phone.")
        status, sid = notify.send_sms(phone, message[:320])
        db.add(SmsMessage(call_id=cid, to_phone=phone, body=message[:320], status=status, twilio_sid=sid))
        db.commit()
    if status == "failed":
        raise ToolError("The text message failed to send. Tell the caller and read the details out instead.")
    return f"SMS sent to {phone}."


@mcp.tool()
async def transfer_to_staff(reason: str, ctx: Context) -> str:
    """Transfer the caller to a human at the front desk. Use for emergencies, prescriptions, billing disputes,
    or when the caller asks for a person. Tell the caller you are transferring them before calling this."""
    cid = call_id(ctx)
    with SessionLocal() as db:
        call = db.get(Call, cid) if cid else None
        if call:
            call.transferred, call.transfer_reason = True, reason[:200]
            db.commit()
        room, ident = (call.room, call.sip_identity) if call else (None, None)
    done = await notify.sip_transfer(room, ident) if room else False
    return "Transferred to staff." if done else "Transfer logged, a staff member will pick up shortly."


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.getenv("MCP_PORT", "8001")),
            json_response=True, stateless_http=True)

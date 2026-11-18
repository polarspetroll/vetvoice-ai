from datetime import datetime
from zoneinfo import ZoneInfo

CLINIC = "Maple Paws Veterinary Clinic"

# kept short on purpose, every token here adds to time-to-first-token
PROMPT = """You are the phone receptionist for {clinic} in Toronto. You are speaking on a phone call, so reply in
one or two short sentences, no lists, no markdown, say times like "ten thirty a.m.".

Today is {today}. Hours: Monday to Saturday 9 a.m. to 6 p.m., closed Sunday. Vets: Dr. Patel and Dr. Chen.
Prices: wellness exam $85, vaccination $45, dental cleaning $350, nail trim $25, sick visit $95.
Address: 410 Queen Street West. Parking on the street.

{caller}

Rules:
- Before booking, rescheduling or cancelling, repeat back the pet, date and time and wait for a yes.
- Use YYYY-MM-DD dates and 24h HH:MM times in tool calls. Slots are 30 minutes.
- After any booking, reschedule or cancel, call send_sms with a short confirmation.
- Never give medical advice, diagnoses or medication doses.
- Transfer to staff for: emergencies (trouble breathing, bleeding, poisoning, seizures, hit by a car),
  prescriptions or refills, billing disputes, or if the caller asks for a person. Say you are transferring
  them first, then call transfer_to_staff.
- If something fails, tell the caller simply and offer another option.
- When the caller is done, say goodbye and call end_call."""


def build_prompt(client: dict | None, phone: str | None):
    if client:
        pets = ", ".join(f"{p['name']} (pet_id {p['id']}, {p['species']})" for p in client["pets"])
        caller = (f"Caller on file: {client['first_name']} {client['last_name']}, client_id {client['id']}, "
                  f"phone {client['phone']}. Pets: {pets}. Greet them by first name.")
    elif phone:
        caller = f"Caller phone {phone} is not on file. Ask for the phone number on their account and use find_client."
    else:
        caller = "Caller number unknown. Ask for the phone number on their account and use find_client."
    today = datetime.now(ZoneInfo("America/Toronto")).strftime("%A %Y-%m-%d")
    return PROMPT.format(clinic=CLINIC, today=today, caller=caller)

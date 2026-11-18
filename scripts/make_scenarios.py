"""writes scenarios.csv (100 test calls). deterministic so re-running gives the same file
day = nth clinic day after the run date (sundays skipped), the runner turns it into a real date"""
import csv
import random
from pathlib import Path

from backend.seed import build, fake_phone

rnd = random.Random(7)
clients = build()
SERVICES = {"exam": "wellness exam", "vaccine": "vaccination", "dental": "dental cleaning",
            "nails": "nail trim", "sick": "sick visit (they've been off their food)"}
TIMES = [f"{h:02d}:{m:02d}" for h in range(9, 18) for m in (0, 30)]
used = set()
rows = []


def slot():
    while True:
        s = (rnd.randint(2, 18), rnd.choice(TIMES))
        if s not in used:
            used.add(s)
            return s


def who(i):
    c = clients[i]
    p = rnd.choice(c.pets)
    return c, p, fake_phone(i)


def add(**kw):
    base = dict(id="", category="", client_phone="", calling_from="", pet_name="", service="", day="", time="",
                new_day="", new_time="", alt_ok=0, vet="", expect="", info_keyword="", caller_goal="")
    base.update(kw)
    rows.append(base)


picks = rnd.sample(range(200), 100)
k = 0

# 40 bookings, 8 of them hit a full slot on purpose
for n in range(40):
    c, p, ph = who(picks[k]); k += 1
    svc = rnd.choice(list(SERVICES))
    day, t = slot()
    conflict = n % 5 == 0
    vet = rnd.choice(["Dr. Patel", "Dr. Chen"]) if n % 7 == 3 else ""
    goal = (f"You are {c.first_name} {c.last_name}. Book a {SERVICES[svc]} for your {p.species} {p.name} "
            f"on {{date}} at {{time}}" + (f" with {vet}" if vet else "") + ". ")
    goal += ("If that time is taken, accept the closest time they offer on the same day. " if conflict else "")
    goal += "Say yes when they read the details back. Say thanks and goodbye once it is booked."
    add(id=f"B{n+1:02d}", category="book", client_phone=ph, pet_name=p.name, service=svc, day=day, time=t,
        alt_ok=int(conflict), vet=vet, expect="booked", caller_goal=goal)

for n in range(15):
    c, p, ph = who(picks[k]); k += 1
    day, t = slot()
    nd, nt = slot()
    goal = (f"You are {c.first_name} {c.last_name}. {p.name} has an appointment on {{date}} at {{time}}. "
            f"You want to move it to {{new_date}} at {{new_time}}. Confirm when asked, then say goodbye.")
    add(id=f"R{n+1:02d}", category="reschedule", client_phone=ph, pet_name=p.name, service="exam", day=day, time=t,
        new_day=nd, new_time=nt, expect="moved", caller_goal=goal)

for n in range(15):
    c, p, ph = who(picks[k]); k += 1
    day, t = slot()
    goal = (f"You are {c.first_name} {c.last_name}. Cancel {p.name}'s appointment on {{date}} at {{time}}, "
            f"you're going out of town. Confirm when asked, then say goodbye.")
    add(id=f"C{n+1:02d}", category="cancel", client_phone=ph, pet_name=p.name, service="vaccine", day=day, time=t,
        expect="cancelled", caller_goal=goal)

INFO = [("What time do you close on Saturday?", "6"), ("Are you open on Sunday?", "closed"),
        ("What are your hours during the week?", "9"), ("What time do you open tomorrow morning?", "9"),
        ("Are you open late on Fridays, like after 7?", "6"),
        ("How much is a wellness exam?", "85"), ("How much do vaccinations cost?", "45"),
        ("What do you charge for a dental cleaning?", "350"), ("How much is a nail trim?", "25"),
        ("How much is a sick visit?", "95"), ("What's the price of a checkup for my cat?", "85"),
        ("How much would a nail trim and a vaccine be together?", "70"),
        ("Is a dental cleaning more than 300 dollars?", "350"),
        ("Where are you located?", "Queen"), ("Is there parking near the clinic?", "street")]
for n, (q, kw) in enumerate(INFO):
    c, p, ph = who(picks[k]); k += 1
    add(id=f"Q{n+1:02d}", category="info", client_phone=ph, expect="no_change", info_keyword=kw,
        caller_goal=f"You are {c.first_name}. Ask: '{q}'. You don't want to book anything. When answered, say thanks and bye.")

URGENT = ["Your dog {pet} just ate a whole chocolate bar and is shaking. You are panicking.",
          "Your dog {pet} was hit by a car ten minutes ago and is bleeding.",
          "Your cat {pet} is breathing really fast with her mouth open.",
          "Your dog {pet} had a seizure a few minutes ago.",
          "{pet} cut a paw badly on glass and it won't stop bleeding.",
          "You need a refill of {pet}'s heart medication prescription.",
          "You want to know if you can double {pet}'s pain medication dose.",
          "You need the vet to renew {pet}'s thyroid prescription.",
          "You were charged twice for {pet}'s last visit and want it fixed.",
          "You think your last bill was wrong, 200 dollars more than quoted, and want to dispute it."]
for n, s in enumerate(URGENT):
    c, p, ph = who(picks[k]); k += 1
    add(id=f"T{n+1:02d}", category="transfer", client_phone=ph, pet_name=p.name, expect="transferred",
        caller_goal=f"You are {c.first_name}. " + s.format(pet=p.name) + " Explain your situation and accept whatever they offer.")

MESSY = ["Keep cutting in while the receptionist is talking, and say 'sorry, sorry' a lot.",
         "Mumble and trail off, say 'um' a lot, and change the time once before settling on {time}.",
         "Start by asking about prices, then interrupt yourself and decide to book.",
         "Speak in very short broken phrases, like a bad phone line.",
         "You are calling from a different phone, your number on file is {phone}. Give it when asked."]
for n, m in enumerate(MESSY):
    c, p, ph = who(picks[k]); k += 1
    day, t = slot()
    goal = (f"You are {c.first_name} {c.last_name}. Book a nail trim for your {p.species} {p.name} on {{date}} "
            f"at {{time}}. " + m.format(time="{time}", phone=" ".join(ph[2:])) + " Confirm when asked, then say bye.")
    add(id=f"M{n+1:02d}", category="messy", client_phone=ph, pet_name=p.name, service="nails", day=day, time=t,
        calling_from="+12895550199" if n == 4 else "", expect="booked", caller_goal=goal)

out = Path(__file__).resolve().parent.parent / "scenarios.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("wrote", len(rows), "scenarios to", out)

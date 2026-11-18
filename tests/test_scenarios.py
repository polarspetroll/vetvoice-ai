import csv
from collections import Counter
from datetime import date
from pathlib import Path

from caller_bot.run_scenarios import clinic_day

ROWS = list(csv.DictReader(open(Path(__file__).parent.parent / "scenarios.csv")))


def test_counts_match_spec():
    assert len(ROWS) == 100
    assert Counter(r["category"] for r in ROWS) == {"book": 40, "reschedule": 15, "cancel": 15, "info": 15,
                                                    "transfer": 10, "messy": 5}


def test_every_scenario_has_an_expected_end_state():
    assert all(r["expect"] for r in ROWS)


def test_no_two_scenarios_share_a_slot():
    slots = [(r["day"], r["time"]) for r in ROWS if r["day"]] + [(r["new_day"], r["new_time"]) for r in ROWS if r["new_day"]]
    assert len(slots) == len(set(slots))


def test_clinic_day_skips_sunday():
    sat = date(2026, 11, 21)
    assert clinic_day(1, sat) == date(2026, 11, 23)
    assert all(clinic_day(n, sat).weekday() != 6 for n in range(1, 30))

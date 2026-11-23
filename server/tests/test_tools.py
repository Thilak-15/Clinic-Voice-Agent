"""Tests for phone parsing and the three tools.  Run:  python -m pytest -q"""

import pytest

from app import db, tools
from app.phone import canonical_phone, normalize_phone

PHONE = "9876543210"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.use_database(tmp_path / "test.db")
    db.init(reset=True)
    yield


def first_free(doctor_name="Rao"):
    res = tools.check_doctor_availability(doctor_name=doctor_name)
    day = res["results"][0]["next_available"][0]
    return day["iso_date"], day["times"][0]


# ----------------------------------------------------------------- phone


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("9876543210", "9876543210"),
        ("98765 43210", "9876543210"),
        ("+91 98765-43210", "9876543210"),
        ("nine eight seven six five four three two one zero", "9876543210"),
        ("nine eight double seven triple five oh one two", "9877555012"),
        ("12345", None),
    ],
)
def test_canonical_phone(spoken, expected):
    assert canonical_phone(spoken) == expected


def test_normalize_mixed():
    assert normalize_phone("98 seven 6") == "9876"


# ---------------------------------------------------------- availability


def test_availability_by_specialty_hint():
    res = tools.check_doctor_availability(specialty="heart")
    assert res["ok"]
    assert [r["doctor"] for r in res["results"]] == ["Dr. Vikram Mehta"]


def test_availability_on_date_lists_times():
    day, _ = first_free()
    res = tools.check_doctor_availability(doctor_name="Dr Rao", date=day)
    assert res["results"][0]["available_times"]


def test_unknown_doctor():
    res = tools.check_doctor_availability(doctor_name="Dr. House")
    assert not res["ok"] and res["error"] == "doctor_not_found"


# --------------------------------------------------------------- booking


def test_booking_requires_confirmation():
    day, t = first_free()
    res = tools.book_appointment(PHONE, "Rao", day, t, phone_confirmed=False)
    assert res["error"] == "phone_not_confirmed"


def test_book_then_slot_disappears():
    day, t = first_free()
    res = tools.book_appointment(PHONE, "Dr. Ananya Rao", day, t, True, "Thilak")
    assert res["ok"], res
    assert res["appointment"]["phone"] == PHONE
    assert len(res["appointment"]["reference"]) == 4

    again = tools.book_appointment("9000000000", "Rao", day, t, True)
    assert again["error"] == "slot_taken"
    assert t not in tools.check_doctor_availability(doctor_name="Rao", date=day)["results"][0][
        "available_times"
    ]


def test_time_without_am_pm():
    # Dr. Iyer only works afternoons, so "2:00" must mean 2 PM.
    res = tools.check_doctor_availability(doctor_name="Iyer")
    day = res["results"][0]["next_available"][0]
    t = day["times"][0]  # e.g. "2:00 PM"
    bare = t.replace(" PM", "")
    booked = tools.book_appointment(PHONE, "Iyer", day["iso_date"], bare, True)
    assert booked["ok"], booked
    assert booked["appointment"]["time"] == t


def test_bad_slot_offers_alternatives():
    day, _ = first_free()
    res = tools.book_appointment(PHONE, "Rao", day, "3:17 AM", True)
    assert res["error"] == "no_such_slot"
    assert res["other_times_that_day"]


# ----------------------------------------------------------- cancelling


def test_cancel_single():
    day, t = first_free()
    tools.book_appointment(PHONE, "Rao", day, t, True)
    res = tools.cancel_appointment("nine eight seven six five four three two one zero", True)
    assert res["ok"], res
    assert res["cancelled"]["status"] == "cancelled"
    # Slot is free again.
    assert t in tools.check_doctor_availability(doctor_name="Rao", date=day)["results"][0][
        "available_times"
    ]


def test_cancel_with_nothing_booked():
    assert tools.cancel_appointment(PHONE, True)["error"] == "no_appointment"


def test_cancel_multiple_needs_reference():
    d1, t1 = first_free("Rao")
    d2, t2 = first_free("Kapoor")
    tools.book_appointment(PHONE, "Rao", d1, t1, True)
    b = tools.book_appointment(PHONE, "Kapoor", d2, t2, True)

    res = tools.cancel_appointment(PHONE, True)
    assert res["error"] == "multiple_appointments"
    assert len(res["appointments"]) == 2

    ref = b["appointment"]["reference"]
    res = tools.cancel_appointment(PHONE, True, appointment_reference=ref)
    assert res["ok"] and res["cancelled"]["doctor"] == "Dr. Meera Kapoor"
    assert len(db.active_appointments_for_phone(PHONE)) == 1

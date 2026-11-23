"""The three tools the LLM can call, plus their JSON schemas.

The logic here is plain synchronous Python with no Pipecat imports, so it can
be unit-tested on its own. bot.py wraps these functions as Pipecat function
handlers.

Every tool returns a dict. On success it has "ok": True; on a problem it has
"ok": False and an "error" the LLM can explain to the caller in its own words.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema

from . import db
from .phone import canonical_phone, spoken

MAX_TIMES_PER_DAY = 8

SPECIALTY_HINTS = {
    "General Physician": ["general", "physician", "gp", "family", "fever", "cold", "checkup"],
    "Cardiologist": ["cardio", "heart", "chest", "bp", "blood pressure"],
    "Dermatologist": ["derma", "skin", "hair", "acne", "rash"],
    "Orthopedic Surgeon": ["ortho", "bone", "joint", "knee", "back", "fracture", "spine"],
    "Pediatrician": ["pediatric", "paediatric", "child", "kid", "baby", "infant"],
}


# ------------------------------------------------------------------ helpers


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_day(d: date) -> str:
    today = db.now().date()
    label = f"{d.strftime('%A')}, {d.day} {d.strftime('%B')}"
    if d == today:
        return f"today ({label})"
    if d == today + timedelta(days=1):
        return f"tomorrow ({label})"
    return label


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", text.lower()) if t not in {"dr", "doctor"}]


def match_doctors(doctor_name: str | None = None, specialty: str | None = None) -> list[dict]:
    doctors = db.list_doctors()
    if doctor_name:
        q = [t for t in _tokens(doctor_name) if len(t) >= 3]
        by_name = [d for d in doctors if any(t in _tokens(d["name"]) for t in q)]
        if by_name:
            return by_name
        if not specialty:
            return []
    if specialty:
        s = specialty.lower()
        return [
            d
            for d in doctors
            if s in d["specialty"].lower()
            or d["specialty"].lower() in s
            or any(h in s for h in SPECIALTY_HINTS.get(d["specialty"], []))
        ]
    return doctors


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    v = value.strip().lower()
    today = db.now().date()
    if v == "today":
        return today
    if v == "tomorrow":
        return today + timedelta(days=1)
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def parse_time_candidates(value: str) -> list[time]:
    """'10:30 am' -> [10:30]; '2:30' -> [02:30, 14:30] (ambiguous, try both)."""
    m = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*([ap])?\.?\s*m?\.?", (value or "").lower())
    if not m:
        return []
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if minute > 59 or hour > 23:
        return []
    if ampm == "p" and hour < 12:
        return [time(hour + 12, minute)]
    if ampm == "a":
        return [time(0 if hour == 12 else hour, minute)]
    if hour < 12:
        return [time(hour, minute), time(hour + 12, minute)]
    return [time(hour, minute)]


def _appointment_view(a: dict) -> dict:
    start = datetime.fromisoformat(a["starts_at"])
    return {
        "appointment_id": a["id"],
        "reference": a["code"],
        "doctor": a["doctor_name"],
        "specialty": a["specialty"],
        "room": a["room"],
        "date": fmt_day(start.date()),
        "time": fmt_time(start),
        "starts_at": a["starts_at"],
        "phone": a["phone"],
        "patient_name": a["patient_name"],
        "status": a["status"],
    }


def _bad_phone(raw: str) -> dict:
    return {
        "ok": False,
        "error": "invalid_phone",
        "message": f"'{raw}' is not a valid 10-digit mobile number. Ask the caller to repeat it.",
    }


def _not_confirmed(phone: str) -> dict:
    return {
        "ok": False,
        "error": "phone_not_confirmed",
        "message": f"Read the number back as {spoken(phone)} and get a clear yes before retrying.",
    }


# -------------------------------------------------------------------- tools


def check_doctor_availability(
    doctor_name: str | None = None, specialty: str | None = None, date: str | None = None
) -> dict:
    doctors = match_doctors(doctor_name, specialty)
    if not doctors:
        return {
            "ok": False,
            "error": "doctor_not_found",
            "message": "No matching doctor. Offer the list of doctors instead.",
            "doctors": [f"{d['name']} ({d['specialty']})" for d in db.list_doctors()],
        }

    wanted = parse_date(date)
    results = []
    for d in doctors:
        free = [datetime.fromisoformat(s["starts_at"]) for s in db.upcoming_slots(d["id"])]
        by_day: dict[date, list[datetime]] = {}
        for t in free:
            by_day.setdefault(t.date(), []).append(t)

        entry = {"doctor_id": d["id"], "doctor": d["name"], "specialty": d["specialty"]}
        if wanted:
            times = by_day.get(wanted, [])
            entry["date"] = fmt_day(wanted)
            entry["available_times"] = [fmt_time(t) for t in times[:MAX_TIMES_PER_DAY]]
            if len(times) > MAX_TIMES_PER_DAY:
                entry["more_times_available"] = len(times) - MAX_TIMES_PER_DAY
            if not times:
                entry["next_available_days"] = [fmt_day(x) for x in sorted(by_day)[:3]]
        else:
            days = sorted(by_day)[:3]
            entry["next_available"] = [
                {"date": fmt_day(x), "iso_date": x.isoformat(),
                 "times": [fmt_time(t) for t in by_day[x][:MAX_TIMES_PER_DAY]]}
                for x in days
            ]  # fmt: skip
        results.append(entry)

    return {"ok": True, "results": results}


def book_appointment(
    phone_number: str,
    doctor_name: str,
    date: str,
    time: str,
    phone_confirmed: bool = False,
    patient_name: str | None = None,
) -> dict:
    phone = canonical_phone(phone_number)
    if not phone:
        return _bad_phone(phone_number)
    if not phone_confirmed:
        return _not_confirmed(phone)

    doctors = match_doctors(doctor_name)
    if len(doctors) != 1:
        return {
            "ok": False,
            "error": "doctor_not_found" if not doctors else "doctor_ambiguous",
            "message": "Confirm which doctor the caller wants.",
            "doctors": [f"{d['name']} ({d['specialty']})" for d in (doctors or db.list_doctors())],
        }
    doctor = doctors[0]

    day = parse_date(date)
    candidates = parse_time_candidates(time)
    if not day or not candidates:
        return {"ok": False, "error": "bad_datetime", "message": "Ask for the date and time again."}

    slot = None
    for t in candidates:
        slot = db.find_slot(doctor["id"], datetime.combine(day, t, db.TZ))
        if slot:
            break

    def alternatives() -> list[str]:
        same_day = [
            datetime.fromisoformat(s["starts_at"])
            for s in db.upcoming_slots(doctor["id"])
            if datetime.fromisoformat(s["starts_at"]).date() == day
        ]
        return [fmt_time(t) for t in same_day[:MAX_TIMES_PER_DAY]]

    if not slot or datetime.fromisoformat(slot["starts_at"]) <= db.now():
        return {
            "ok": False,
            "error": "no_such_slot",
            "message": f"{doctor['name']} has no slot at that time on {fmt_day(day)}.",
            "other_times_that_day": alternatives(),
        }

    appt_id = db.book_slot(slot["id"], doctor["id"], phone, (patient_name or "").strip() or None)
    if appt_id is None:
        return {
            "ok": False,
            "error": "slot_taken",
            "message": "That slot was just taken.",
            "other_times_that_day": alternatives(),
        }

    return {"ok": True, "appointment": _appointment_view(db.get_appointment(appt_id))}


def cancel_appointment(
    phone_number: str, phone_confirmed: bool = False, appointment_reference: str | None = None
) -> dict:
    phone = canonical_phone(phone_number)
    if not phone:
        return _bad_phone(phone_number)
    if not phone_confirmed:
        return _not_confirmed(phone)

    active = db.active_appointments_for_phone(phone)
    if not active:
        return {
            "ok": False,
            "error": "no_appointment",
            "message": f"No upcoming appointment is booked under {spoken(phone)}.",
        }

    if appointment_reference:
        ref = re.sub(r"\D", "", appointment_reference)
        chosen = [a for a in active if a["code"] == ref]
        if not chosen:
            return {
                "ok": False,
                "error": "reference_not_found",
                "message": "That reference doesn't match. Ask which appointment to cancel.",
                "appointments": [_appointment_view(a) for a in active],
            }
        target = chosen[0]
    elif len(active) > 1:
        return {
            "ok": False,
            "error": "multiple_appointments",
            "message": "The caller has several appointments. Ask which one to cancel, "
            "then call again with its reference.",
            "appointments": [_appointment_view(a) for a in active],
        }
    else:
        target = active[0]

    if not db.cancel(target["id"]):
        return {"ok": False, "error": "already_cancelled", "message": "Already cancelled."}
    return {"ok": True, "cancelled": _appointment_view(db.get_appointment(target["id"]))}


# ------------------------------------------------------------------ schemas

_PHONE = {
    "type": "string",
    "description": "Caller's 10-digit mobile number as digits only, e.g. '9876543210'.",
}
_CONFIRMED = {
    "type": "boolean",
    "description": "True only after you read the number back and the caller said yes.",
}

check_availability_schema = FunctionSchema(
    name="check_doctor_availability",
    description=(
        "Look up free appointment slots. Filter by doctor name, by specialty, and/or by date. "
        "With no date, returns the next few days that have free slots."
    ),
    properties={
        "doctor_name": {"type": "string", "description": "Doctor's name, e.g. 'Dr. Mehta'."},
        "specialty": {
            "type": "string",
            "description": "Speciality or health concern, e.g. 'cardiologist' or 'skin'.",
        },
        "date": {"type": "string", "description": "Date as YYYY-MM-DD."},
    },
    required=[],
)

book_appointment_schema = FunctionSchema(
    name="book_appointment",
    description="Book a free slot for the caller. Only call after the phone number is confirmed.",
    properties={
        "phone_number": _PHONE,
        "phone_confirmed": _CONFIRMED,
        "doctor_name": {"type": "string", "description": "Doctor's name."},
        "date": {"type": "string", "description": "Date as YYYY-MM-DD."},
        "time": {"type": "string", "description": "Slot start time, e.g. '10:30 AM'."},
        "patient_name": {"type": "string", "description": "Patient's name, if given."},
    },
    required=["phone_number", "phone_confirmed", "doctor_name", "date", "time"],
)

cancel_appointment_schema = FunctionSchema(
    name="cancel_appointment",
    description=(
        "Cancel the caller's upcoming appointment, found by phone number. If they have more than "
        "one, the tool returns the list so you can ask which one."
    ),
    properties={
        "phone_number": _PHONE,
        "phone_confirmed": _CONFIRMED,
        "appointment_reference": {
            "type": "string",
            "description": "4-digit reference, only when choosing between several appointments.",
        },
    },
    required=["phone_number", "phone_confirmed"],
)

TOOLS = ToolsSchema(
    standard_tools=[check_availability_schema, book_appointment_schema, cancel_appointment_schema]
)

HANDLERS = {
    "check_doctor_availability": check_doctor_availability,
    "book_appointment": book_appointment,
    "cancel_appointment": cancel_appointment,
}

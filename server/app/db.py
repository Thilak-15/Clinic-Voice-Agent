"""SQLite storage for doctors, slots and appointments.

Everything is mock data. On first start (or on reset) we generate a week of
30-minute slots for each doctor, starting from today, so the demo always has
future availability no matter when it is run.
"""

from __future__ import annotations

import random
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.CLINIC_TIMEZONE)

# id, name, specialty, working days (0=Mon), start hour, end hour, room
DOCTORS = [
    ("d1", "Dr. Ananya Rao", "General Physician", [0, 1, 2, 3, 4, 5], 9, 13, "Room 101"),
    ("d2", "Dr. Vikram Mehta", "Cardiologist", [0, 2, 4], 10, 15, "Room 204"),
    ("d3", "Dr. Sara Thomas", "Dermatologist", [1, 3, 5], 11, 17, "Room 112"),
    ("d4", "Dr. Arjun Iyer", "Orthopedic Surgeon", [0, 1, 3, 4], 14, 18, "Room 305"),
    ("d5", "Dr. Meera Kapoor", "Pediatrician", [0, 1, 2, 3, 4], 9, 12, "Room 118"),
]

SLOT_MINUTES = 30
DAYS_AHEAD = 7

_lock = threading.Lock()


def now() -> datetime:
    return datetime.now(TZ)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = _connect(config.DB_PATH)
    return _conn


def use_database(path: Path | str) -> None:
    """Point the module at a different database file (used by tests)."""
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = _connect(Path(path))


@contextmanager
def tx():
    """Serialised transaction. The bot and the HTTP API share one connection."""
    conn = get_conn()
    with _lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    specialty TEXT NOT NULL,
    room      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id TEXT NOT NULL REFERENCES doctors(id),
    starts_at TEXT NOT NULL,            -- ISO 8601 with offset
    is_booked INTEGER NOT NULL DEFAULT 0,
    UNIQUE (doctor_id, starts_at)
);
CREATE TABLE IF NOT EXISTS appointments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT NOT NULL UNIQUE,  -- short reference read out to the caller
    slot_id      INTEGER NOT NULL REFERENCES slots(id),
    doctor_id    TEXT NOT NULL REFERENCES doctors(id),
    phone        TEXT NOT NULL,
    patient_name TEXT,
    status       TEXT NOT NULL CHECK (status IN ('booked', 'cancelled')),
    created_at   TEXT NOT NULL,
    cancelled_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_appt_phone ON appointments(phone, status);
"""


def init(reset: bool = False) -> None:
    with tx() as conn:
        if reset:
            conn.executescript(
                "DROP TABLE IF EXISTS appointments; DROP TABLE IF EXISTS slots; "
                "DROP TABLE IF EXISTS doctors;"
            )
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
            _seed(conn)
        else:
            _top_up_slots(conn)


def _slot_times(start: date, days: int):
    for offset in range(days):
        day = start + timedelta(days=offset)
        for doc_id, _n, _s, workdays, h0, h1, _r in DOCTORS:
            if day.weekday() not in workdays:
                continue
            t = datetime.combine(day, time(h0), TZ)
            end = datetime.combine(day, time(h1), TZ)
            while t < end:
                yield doc_id, t
                t += timedelta(minutes=SLOT_MINUTES)


def _seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO doctors (id, name, specialty, room) VALUES (?, ?, ?, ?)",
        [(d[0], d[1], d[2], d[6]) for d in DOCTORS],
    )
    # About a third of slots are already taken by "other patients", so the
    # schedule looks realistic. Seeded so every reset looks the same.
    rng = random.Random(42)
    rows = [
        (doc_id, t.isoformat(), 1 if rng.random() < 0.33 else 0)
        for doc_id, t in _slot_times(now().date(), DAYS_AHEAD)
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO slots (doctor_id, starts_at, is_booked) VALUES (?, ?, ?)", rows
    )


def _top_up_slots(conn: sqlite3.Connection) -> None:
    """Keep a rolling week of slots when the server runs on later days."""
    rows = [(doc_id, t.isoformat()) for doc_id, t in _slot_times(now().date(), DAYS_AHEAD)]
    conn.executemany("INSERT OR IGNORE INTO slots (doctor_id, starts_at) VALUES (?, ?)", rows)


# ---------------------------------------------------------------- queries


def list_doctors() -> list[dict]:
    rows = get_conn().execute("SELECT * FROM doctors ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_doctor(doctor_id: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
    return dict(row) if row else None


def upcoming_slots(doctor_id: str | None = None, only_free: bool = True) -> list[dict]:
    sql = "SELECT * FROM slots WHERE starts_at > ?"
    args: list = [now().isoformat()]
    if doctor_id:
        sql += " AND doctor_id = ?"
        args.append(doctor_id)
    if only_free:
        sql += " AND is_booked = 0"
    sql += " ORDER BY starts_at"
    return [dict(r) for r in get_conn().execute(sql, args).fetchall()]


def find_slot(doctor_id: str, starts_at: datetime) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM slots WHERE doctor_id = ? AND starts_at = ?",
        (doctor_id, starts_at.isoformat()),
    ).fetchone()
    return dict(row) if row else None


def _appointment_query(where: str = "", order: str = "s.starts_at") -> str:
    return f"""
        SELECT a.id, a.code, a.slot_id, a.doctor_id, a.phone, a.patient_name, a.status,
               a.created_at, a.cancelled_at, s.starts_at,
               d.name AS doctor_name, d.specialty, d.room
        FROM appointments a
        JOIN slots s ON s.id = a.slot_id
        JOIN doctors d ON d.id = a.doctor_id
        {where}
        ORDER BY {order}
    """


def list_appointments() -> list[dict]:
    sql = _appointment_query(order="a.created_at DESC")
    return [dict(r) for r in get_conn().execute(sql).fetchall()]


def get_appointment(appointment_id: int) -> dict | None:
    row = get_conn().execute(_appointment_query("WHERE a.id = ?"), (appointment_id,)).fetchone()
    return dict(row) if row else None


def active_appointments_for_phone(phone: str) -> list[dict]:
    sql = _appointment_query("WHERE a.phone = ? AND a.status = 'booked' AND s.starts_at > ?")
    return [dict(r) for r in get_conn().execute(sql, (phone, now().isoformat())).fetchall()]


def _new_code(conn: sqlite3.Connection) -> str:
    rng = random.SystemRandom()
    while True:
        code = f"{rng.randint(1000, 9999)}"
        if not conn.execute("SELECT 1 FROM appointments WHERE code = ?", (code,)).fetchone():
            return code


def book_slot(slot_id: int, doctor_id: str, phone: str, patient_name: str | None) -> int | None:
    """Atomically claim a slot. Returns the appointment id, or None if taken."""
    with tx() as conn:
        cur = conn.execute(
            "UPDATE slots SET is_booked = 1 WHERE id = ? AND is_booked = 0", (slot_id,)
        )
        if cur.rowcount == 0:
            return None
        cur = conn.execute(
            """INSERT INTO appointments
               (code, slot_id, doctor_id, phone, patient_name, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'booked', ?)""",
            (_new_code(conn), slot_id, doctor_id, phone, patient_name, now().isoformat()),
        )
        return cur.lastrowid


def cancel(appointment_id: int) -> bool:
    with tx() as conn:
        row = conn.execute(
            "SELECT slot_id FROM appointments WHERE id = ? AND status = 'booked'",
            (appointment_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE appointments SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
            (now().isoformat(), appointment_id),
        )
        conn.execute("UPDATE slots SET is_booked = 0 WHERE id = ?", (row["slot_id"],))
        return True

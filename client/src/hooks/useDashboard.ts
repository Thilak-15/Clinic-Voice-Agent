import { useCallback, useEffect, useRef, useState } from 'react';

import { api, type Appointment, type Doctor, type Meta, type ServerEvent } from '../lib/api';
import { setTimezone } from '../lib/format';

export type Highlights = {
  doctors: Set<string>; // doctors the agent is looking at right now
  appointments: Map<number, 'booked' | 'cancelled'>; // rows that just changed
};

const empty = (): Highlights => ({ doctors: new Set(), appointments: new Map() });

/**
 * Loads doctors + appointments and keeps them fresh.
 * The server pushes events over SSE; on each one we refetch and briefly
 * highlight whatever changed.
 */
export function useDashboard() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [live, setLive] = useState(false);
  const [onCall, setOnCall] = useState(false);
  const [highlights, setHighlights] = useState<Highlights>(empty);
  // seq changes on every event, so the schedule jumps even to the same day again.
  const [focusDay, setFocusDay] = useState<{ day: string; seq: number } | null>(null);
  const focusSeq = useRef(0);
  const focus = useCallback((day: string) => setFocusDay({ day, seq: ++focusSeq.current }), []);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [d, a] = await Promise.all([api.doctors(), api.appointments()]);
      setDoctors(d);
      setAppointments(a);
      setError(null);
    } catch {
      setError('Can’t reach the server. Is it running on port 7860?');
    }
  }, []);

  const flash = useCallback((apply: (h: Highlights) => void, undo: (h: Highlights) => void, ms: number) => {
    setHighlights((h) => {
      const next = { doctors: new Set(h.doctors), appointments: new Map(h.appointments) };
      apply(next);
      return next;
    });
    timers.current.push(
      window.setTimeout(
        () =>
          setHighlights((h) => {
            const next = { doctors: new Set(h.doctors), appointments: new Map(h.appointments) };
            undo(next);
            return next;
          }),
        ms,
      ),
    );
  }, []);

  useEffect(() => {
    api
      .meta()
      .then((m) => {
        setTimezone(m.timezone);
        setMeta(m);
      })
      .catch(() => {});
    void refresh();

    const es = api.events();
    es.onopen = () => setLive(true);
    es.onerror = () => setLive(false);
    es.onmessage = (msg) => {
      const ev = JSON.parse(msg.data) as ServerEvent;
      switch (ev.type) {
        case 'availability_checked':
          if (ev.date) focus(ev.date);
          flash(
            (h) => ev.doctor_ids.forEach((id) => h.doctors.add(id)),
            (h) => ev.doctor_ids.forEach((id) => h.doctors.delete(id)),
            6000,
          );
          break;
        case 'appointment_booked':
        case 'appointment_cancelled': {
          const a = ev.appointment;
          const kind = ev.type === 'appointment_booked' ? 'booked' : 'cancelled';
          void refresh().then(() => {
            focus(a.starts_at.slice(0, 10));
            flash(
              (h) => h.appointments.set(a.appointment_id, kind),
              (h) => h.appointments.delete(a.appointment_id),
              5000,
            );
          });
          break;
        }
        case 'call_started':
          setOnCall(true);
          break;
        case 'call_ended':
          setOnCall(false);
          break;
        case 'data_reset':
          void refresh();
          break;
      }
    };

    // Slots in the past drop off; a light refresh each minute keeps the board honest.
    const tick = window.setInterval(refresh, 60_000);
    return () => {
      es.close();
      window.clearInterval(tick);
      timers.current.forEach(window.clearTimeout);
    };
  }, [refresh, flash, focus]);

  const reset = useCallback(async () => {
    await api.reset();
    await refresh();
  }, [refresh]);

  return { meta, doctors, appointments, live, onCall, highlights, focusDay, error, reset };
}
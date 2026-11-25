import { useEffect, useMemo, useState } from 'react';

import type { Highlights } from '../hooks/useDashboard';
import type { Appointment, Doctor } from '../lib/api';
import { dayKey, dayNum, initials, month, time, weekday } from '../lib/format';

type Props = {
  doctors: Doctor[];
  appointments: Appointment[];
  highlights: Highlights;
  focusDay: { day: string; seq: number } | null;
  agent: string;
};

export function Schedule({ doctors, appointments, highlights, focusDay, agent }: Props) {
  // Every day that has slots, with its count of free ones.
  const days = useMemo(() => {
    const map = new Map<string, { key: string; date: string; free: number }>();
    for (const d of doctors)
      for (const s of d.slots) {
        const key = dayKey(s.starts_at);
        const entry = map.get(key) ?? { key, date: s.starts_at, free: 0 };
        if (!s.booked) entry.free++;
        map.set(key, entry);
      }
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key));
  }, [doctors]);

  const [selected, setSelected] = useState<string | null>(null);
  const day = selected && days.some((d) => d.key === selected) ? selected : days[0]?.key;

  // Jump to the day of a booking/cancellation that just came in.
  useEffect(() => {
    if (focusDay) setSelected(focusDay.day);
  }, [focusDay]);

  // Slots whose appointment just changed get a flash.
  const flashSlots = useMemo(() => {
    const m = new Map<number, 'booked' | 'cancelled'>();
    for (const a of appointments) {
      const k = highlights.appointments.get(a.id);
      if (k) m.set(a.slot_id, k);
    }
    return m;
  }, [appointments, highlights]);

  // Which booked slots were booked through the agent (vs. pre-seeded "other patients").
  const voiceBooked = useMemo(
    () => new Set(appointments.filter((a) => a.status === 'booked').map((a) => a.slot_id)),
    [appointments],
  );

  return (
    <section className="panel schedule">
      <div className="panel__head">
        <h2>Schedule</h2>
        <div className="legend">
          <span><i className="lg lg--free" />Open</span>
          <span><i className="lg lg--taken" />Taken</span>
          <span><i className="lg lg--voice" />Booked by {agent}</span>
        </div>
      </div>

      <div className="days" role="tablist">
        {days.map((d) => (
          <button
            key={d.key}
            role="tab"
            aria-selected={d.key === day}
            className={`day ${d.key === day ? 'is-active' : ''}`}
            onClick={() => setSelected(d.key)}
          >
            <span className="day__wd">{weekday(d.date)}</span>
            <span className="day__num">{dayNum(d.date)}</span>
            <span className="day__mo">{month(d.date)}</span>
            <span className="day__free">{d.free} open</span>
          </button>
        ))}
      </div>

      <ul className="doctors">
        {doctors.map((doc) => {
          const slots = doc.slots.filter((s) => dayKey(s.starts_at) === day);
          const free = slots.filter((s) => !s.booked).length;
          const checking = highlights.doctors.has(doc.id);
          return (
            <li key={doc.id} className={`doc ${checking ? 'is-checking' : ''}`}>
              <div className="doc__who">
                <span className="doc__avatar">{initials(doc.name)}</span>
                <div>
                  <div className="doc__name">{doc.name}</div>
                  <div className="doc__spec">
                    {doc.specialty} <span className="sep">·</span> {doc.room}
                  </div>
                </div>
                {checking ? (
                  <span className="doc__flag">{agent} is looking</span>
                ) : (
                  <span className="doc__count">{slots.length ? `${free}/${slots.length}` : ''}</span>
                )}
              </div>
              <div className="slots">
                {slots.length === 0 && <span className="slots__off">Not in clinic</span>}
                {slots.map((s) => {
                  const fl = flashSlots.get(s.id);
                  const cls = s.booked ? (voiceBooked.has(s.id) ? 'slot--voice' : 'slot--taken') : 'slot--free';
                  return (
                    <span
                      key={s.id}
                      className={`slot ${cls} ${fl ? `flash-${fl}` : ''}`}
                      title={s.booked ? 'Taken' : 'Open'}
                    >
                      {time(s.starts_at).replace(' ', ' ')}
                    </span>
                  );
                })}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
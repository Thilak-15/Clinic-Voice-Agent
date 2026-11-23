import { useMemo, useState } from 'react';

import type { Highlights } from '../hooks/useDashboard';
import type { Appointment } from '../lib/api';
import { phone, shortDateTime } from '../lib/format';

type Props = { appointments: Appointment[]; highlights: Highlights };
type Filter = 'all' | 'booked' | 'cancelled';

export function Appointments({ appointments, highlights }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const rows = useMemo(
    () => appointments.filter((a) => filter === 'all' || a.status === filter),
    [appointments, filter],
  );
  const count = (f: Filter) => (f === 'all' ? appointments.length : appointments.filter((a) => a.status === f).length);

  return (
    <section className="panel appts">
      <div className="panel__head">
        <h2>Appointments</h2>
        <div className="seg-ctrl" role="tablist">
          {(['all', 'booked', 'cancelled'] as Filter[]).map((f) => (
            <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? 'is-active' : ''} onClick={() => setFilter(f)}>
              {f[0].toUpperCase() + f.slice(1)} <span>{count(f)}</span>
            </button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="empty">
          <div className="empty__art" aria-hidden>
            <span /><span /><span />
          </div>
          <p>{appointments.length ? 'Nothing here.' : 'No appointments yet. Start a call and book one.'}</p>
        </div>
      ) : (
        <ol className="appt-list">
          {rows.map((a) => {
            const flash = highlights.appointments.get(a.id);
            return (
              <li key={a.id} className={`appt appt--${a.status} ${flash ? `flash-${flash}` : ''}`}>
                <div className="appt__when">
                  <span className="mono">{shortDateTime(a.starts_at)}</span>
                </div>
                <div className="appt__main">
                  <div className="appt__patient">{a.patient_name || 'Unnamed patient'}</div>
                  <div className="appt__sub">
                    <span className="mono">{phone(a.phone)}</span>
                    <span className="sep">·</span>
                    {a.doctor_name}
                  </div>
                </div>
                <div className="appt__side">
                  <span className={`badge badge--${a.status}`}>{a.status === 'booked' ? 'Booked' : 'Cancelled'}</span>
                  <span className="appt__ref mono">#{a.code}</span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

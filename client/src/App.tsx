import { useEffect, useMemo, useState } from 'react';

import { Appointments } from './components/Appointments';
import { PhoneIcon, ResetIcon } from './components/Icons';
import { Phone } from './components/Phone';
import { Schedule } from './components/Schedule';
import { useCall } from './hooks/useCall';
import { useDashboard } from './hooks/useDashboard';
import { clock, dayKey, longDate } from './lib/format';

export default function App() {
  const dash = useDashboard();
  const call = useCall();
  const [now, setNow] = useState(new Date());
  const agent = dash.meta?.agent ?? 'Maya';
  const clinic = dash.meta?.clinic ?? 'Sunrise Health Clinic';
  const phoneOpen = call.status !== 'idle';
  const inCall = call.status === 'ringing' || call.status === 'connected';

  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 15_000);
    return () => window.clearInterval(t);
  }, []);

  const stats = useMemo(() => {
    const today = dayKey(new Date());
    const open = dash.doctors.reduce((n, d) => n + d.slots.filter((s) => !s.booked).length, 0);
    const inToday = dash.doctors.filter((d) => d.slots.some((s) => dayKey(s.starts_at) === today)).length;
    const booked = dash.appointments.filter((a) => a.status === 'booked').length;
    const cancelled = dash.appointments.filter((a) => a.status === 'cancelled').length;
    return [
      { label: 'Open slots', sub: 'next 7 days', value: open },
      { label: 'Doctors in', sub: 'today', value: inToday },
      { label: `Booked by ${agent}`, sub: 'active', value: booked },
      { label: 'Cancelled', sub: 'by callers', value: cancelled },
    ];
  }, [dash.doctors, dash.appointments, agent]);

  const [brand, ...rest] = clinic.split(' ');

  return (
    <div className={`app ${phoneOpen ? 'with-phone' : ''}`}>
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden>
            <rect width="32" height="32" rx="8" fill="var(--accent)" />
            <path d="M6 20a10 10 0 0 1 20 0" fill="none" stroke="var(--paper)" strokeWidth="2.5" strokeLinecap="round" />
            <path d="M4 24h24" stroke="var(--paper)" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="16" cy="20" r="3" fill="var(--amber)" />
          </svg>
          <span className="brand__name">
            {brand} <em>{rest.join(' ')}</em>
          </span>
        </div>

        <div className={`presence ${dash.onCall || inCall ? 'is-busy' : ''} ${dash.live ? '' : 'is-off'}`}>
          <i />
          {!dash.live ? 'Offline' : dash.onCall || inCall ? `${agent} is on a call` : `${agent} is available`}
        </div>

        <div className="topbar__right">
          <span className="clock mono">{clock(now)} IST</span>
          <button className="icon-btn" onClick={dash.reset} title="Reset demo data" aria-label="Reset demo data">
            <ResetIcon size={18} />
          </button>
          <button className="cta" onClick={call.start} disabled={inCall}>
            <PhoneIcon size={18} />
            {inCall ? 'On call' : 'Try call'}
          </button>
        </div>
      </header>

      <main className="main">
        <div className="intro">
          <div>
            <p className="eyebrow">Front desk</p>
            <h1>{longDate(now)}</h1>
          </div>
          <dl className="stats">
            {stats.map((s) => (
              <div key={s.label} className="stat">
                <dt>
                  {s.label}
                  <span>{s.sub}</span>
                </dt>
                <dd>{s.value}</dd>
              </div>
            ))}
          </dl>
        </div>

        {dash.error && <div className="banner">{dash.error}</div>}

        <div className="grid">
          <Schedule
            doctors={dash.doctors}
            appointments={dash.appointments}
            highlights={dash.highlights}
            focusDay={dash.focusDay}
            agent={agent}
          />
          <Appointments appointments={dash.appointments} highlights={dash.highlights} />
        </div>

        <footer className="foot">
          Voice by ElevenLabs · Reasoning by {dash.meta?.llm ?? 'Gemini'} · Pipeline by Pipecat
        </footer>
      </main>

      <Phone call={call} agent={agent} clinic={clinic} />
    </div>
  );
}

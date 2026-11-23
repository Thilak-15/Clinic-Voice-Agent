import { useEffect, useRef, useState } from 'react';

import type { CallApi, Turn } from '../hooks/useCall';
import { clock, duration, phone as fmtPhone } from '../lib/format';
import { CheckIcon, HangUpIcon, MicIcon, MicOffIcon, PhoneIcon, XIcon } from './Icons';
import { Waveform } from './Waveform';

type Props = { call: CallApi; agent: string; clinic: string };

export function Phone({ call, agent, clinic }: Props) {
  const { status, startedAt, endedAt, turns, activity, speaker, muted, error } = call;
  const open = status !== 'idle';
  const [now, setNow] = useState(Date.now());
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(t);
  }, []);

  // Keep the newest line in view.
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [turns, activity]);

  const label =
    status === 'ringing'
      ? 'Calling…'
      : status === 'connected' && startedAt
        ? duration(now - startedAt)
        : status === 'ended'
          ? `Call ended${startedAt && endedAt ? ` · ${duration(endedAt - startedAt)}` : ''}`
          : status === 'error'
            ? 'Call failed'
            : '';

  return (
    <aside className={`phone phone--${status} ${open ? 'is-open' : ''}`} aria-hidden={!open} aria-label="Call">
      {/* The agent's voice plays through this element. */}
      <audio ref={call.audioEl} autoPlay playsInline />
      <div className="phone__body">
        <div className="phone__statusbar">
          <span>{clock(new Date(now))}</span>
          <span className="phone__island" />
          <span className="phone__signal" aria-hidden>
            <i /><i /><i /><i />
          </span>
        </div>

        <header className="phone__caller">
          <div className={`avatar ${speaker === 'bot' ? 'is-speaking' : ''}`}>
            <span>{agent[0]}</span>
            {status === 'ringing' && (
              <>
                <b className="ring r1" />
                <b className="ring r2" />
              </>
            )}
          </div>
          <h2>{agent}</h2>
          <p className="phone__clinic">{clinic}</p>
          <p className="phone__state" aria-live="polite">{label}</p>
        </header>

        <div className="phone__wave">
          <Waveform levels={call.levels} active={status === 'connected'} />
        </div>

        <div className="phone__transcript" ref={scroller}>
          {status === 'ringing' && <p className="hint">Connecting to the front desk</p>}
          {status === 'connected' && turns.length === 0 && <p className="hint">Say hello when you hear {agent}</p>}
          {turns.map((t) => (
            <TurnView key={t.id} turn={t} />
          ))}
          {activity && (
            <div className="activity">
              <span className="dots"><i /><i /><i /></span>
              {activity}
            </div>
          )}
          {status === 'error' && error && <p className="hint hint--error">{error}</p>}
        </div>

        <footer className="phone__controls">
          {status === 'ringing' || status === 'connected' ? (
            <>
              <button
                className={`round ${muted ? 'is-on' : ''}`}
                onClick={call.toggleMute}
                disabled={status !== 'connected'}
                aria-pressed={muted}
              >
                {muted ? <MicOffIcon size={22} /> : <MicIcon size={22} />}
                <span>{muted ? 'Unmute' : 'Mute'}</span>
              </button>
              <button className="round round--end" onClick={call.end}>
                <HangUpIcon size={26} />
                <span>End</span>
              </button>
            </>
          ) : (
            <>
              <button className="round" onClick={call.dismiss}>
                <XIcon size={22} />
                <span>Close</span>
              </button>
              <button className="round round--call" onClick={call.start}>
                <PhoneIcon size={22} />
                <span>Call again</span>
              </button>
            </>
          )}
        </footer>
        <div className="phone__home" />
      </div>
    </aside>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  if (turn.role === 'user') {
    return (
      <div className="bubble bubble--user">
        {turn.text}
        {turn.interim && <span className="interim">{turn.text ? ' ' : ''}{turn.interim}</span>}
      </div>
    );
  }
  if (turn.role === 'bot') {
    return (
      <div className="bubble bubble--bot">
        {turn.segments.map((s) => (
          <span key={s.id} className="seg">
            <span className="spoken">{s.text.slice(0, Math.max(s.spoken.length, 0))}</span>
            <span className="unspoken">{s.text.slice(s.spoken.length)}</span>{' '}
          </span>
        ))}
      </div>
    );
  }
  const a = turn.appointment;
  const booked = turn.kind === 'booked';
  return (
    <div className={`ticket ${booked ? '' : 'ticket--cancel'}`}>
      <div className="ticket__head">
        <span className="ticket__badge">{booked ? <CheckIcon size={14} /> : <XIcon size={14} />}</span>
        {booked ? 'Appointment booked' : 'Appointment cancelled'}
        <span className="ticket__ref">#{a.reference}</span>
      </div>
      <div className="ticket__doc">{a.doctor}</div>
      <div className="ticket__meta">
        <span>{a.date.replace(/^(today|tomorrow) \((.*)\)$/, '$2')}</span>
        <span>{a.time}</span>
      </div>
      <div className="ticket__foot">
        <span>{a.patient_name || 'Patient'}</span>
        <span className="mono">{fmtPhone(a.phone)}</span>
      </div>
    </div>
  );
}

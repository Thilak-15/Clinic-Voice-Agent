// All times are shown in the clinic's timezone, whatever the viewer's laptop says.
let TZ = 'Asia/Kolkata';
export const setTimezone = (tz: string) => (TZ = tz);

const fmt = (opts: Intl.DateTimeFormatOptions) => (iso: string | Date) =>
  new Intl.DateTimeFormat('en-IN', { timeZone: TZ, ...opts }).format(new Date(iso));

/** 2026-11-24 in clinic time; used to group slots by day. */
export const dayKey = (iso: string | Date) =>
  new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(
    new Date(iso),
  );

export const time = (iso: string) => fmt({ hour: 'numeric', minute: '2-digit', hour12: true })(iso).toUpperCase();
export const weekday = (iso: string | Date) => fmt({ weekday: 'short' })(iso);
export const dayNum = (iso: string | Date) => fmt({ day: 'numeric' })(iso);
export const month = (iso: string | Date) => fmt({ month: 'short' })(iso);
export const longDate = (iso: string | Date) => fmt({ weekday: 'long', day: 'numeric', month: 'long' })(iso);
export const shortDateTime = (iso: string) => `${fmt({ day: 'numeric', month: 'short' })(iso)} · ${time(iso)}`;
export const clock = (d: Date) => fmt({ hour: '2-digit', minute: '2-digit', hour12: false })(d);

/** 9876543210 -> 98765 43210 */
export const phone = (p: string) => (p.length === 10 ? `${p.slice(0, 5)} ${p.slice(5)}` : p);

export const duration = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

export const initials = (name: string) =>
  name
    .replace(/^Dr\.?\s*/i, '')
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join('');

// REST + SSE client for the Python server.
// VITE_API_URL is empty in dev (Vite proxies /api) and when the server hosts the build.
export const API = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '';

export type Slot = { id: number; starts_at: string; booked: boolean };
export type Doctor = { id: string; name: string; specialty: string; room: string; slots: Slot[] };
export type Appointment = {
  id: number;
  code: string;
  slot_id: number;
  doctor_id: string;
  doctor_name: string;
  specialty: string;
  room: string;
  phone: string;
  patient_name: string | null;
  status: 'booked' | 'cancelled';
  starts_at: string;
  created_at: string;
  cancelled_at: string | null;
};
export type Meta = { clinic: string; agent: string; timezone: string; now: string; llm: string };

// What the bot sends: over SSE to every dashboard, and as RTVI server messages to the caller.
export type BookingView = {
  appointment_id: number;
  reference: string;
  doctor: string;
  specialty: string;
  room: string;
  date: string;
  time: string;
  starts_at: string;
  phone: string;
  patient_name: string | null;
  status: string;
};
export type ServerEvent =
  | { type: 'availability_checked'; doctor_ids: string[] }
  | { type: 'appointment_booked'; appointment: BookingView }
  | { type: 'appointment_cancelled'; appointment: BookingView }
  | { type: 'tool_started'; tool: string }
  | { type: 'call_started' | 'call_ended' | 'data_reset' };

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export const api = {
  meta: () => get<Meta>('/api/meta'),
  doctors: () => get<Doctor[]>('/api/doctors'),
  appointments: () => get<Appointment[]>('/api/appointments'),
  reset: () => fetch(`${API}/api/reset`, { method: 'POST' }),
  events: () => new EventSource(`${API}/api/events`),
  offerUrl: `${API}/api/offer`,
};

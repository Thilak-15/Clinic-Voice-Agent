import { PipecatClient, type BotOutputData, type TranscriptData } from '@pipecat-ai/client-js';
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport';
import { useCallback, useEffect, useRef, useState } from 'react';

import { api, type BookingView, type ServerEvent } from '../lib/api';
import * as sounds from '../lib/sounds';

export type CallStatus = 'idle' | 'ringing' | 'connected' | 'ended' | 'error';

/** One bubble in the transcript. Bot text arrives in sentence segments. */
export type Turn =
  | { id: number; role: 'user'; text: string; interim: string }
  | { id: number; role: 'bot'; segments: { id: number; text: string; spoken: string }[] }
  | { id: number; role: 'card'; kind: 'booked' | 'cancelled'; appointment: BookingView };

const TOOL_LABEL: Record<string, string> = {
  check_doctor_availability: 'Checking the schedule',
  book_appointment: 'Booking the slot',
  cancel_appointment: 'Cancelling',
};

const MIN_RING_MS = 1600; // let the phone ring a little, even when the bot is instant

/**
 * Owns one voice call: the Pipecat client, the transcript, call state and
 * whatever the bot pushes to the phone (tool activity, booking cards).
 */
export function useCall() {
  const [status, setStatus] = useState<CallStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [endedAt, setEndedAt] = useState<number | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activity, setActivity] = useState<string | null>(null);
  const [speaker, setSpeaker] = useState<'user' | 'bot' | null>(null);

  // Audio levels change ~50x a second; keep them in refs so the waveform
  // canvas reads them without re-rendering React.
  const levels = useRef({ user: 0, bot: 0 });
  const client = useRef<PipecatClient | null>(null);
  const audioEl = useRef<HTMLAudioElement | null>(null);
  const statusRef = useRef<CallStatus>('idle');
  const nextId = useRef(1);

  const setStat = (s: CallStatus) => {
    statusRef.current = s;
    setStatus(s);
  };

  // ------------------------------------------------------------ transcript

  const onUserTranscript = useCallback((d: TranscriptData) => {
    const text = d.text.trim();
    if (!text) return;
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      const turn =
        last?.role === 'user' ? { ...last } : { id: nextId.current++, role: 'user' as const, text: '', interim: '' };
      if (d.final) {
        turn.text = turn.text ? `${turn.text} ${text}` : text;
        turn.interim = '';
      } else {
        turn.interim = text;
      }
      return last?.role === 'user' ? [...prev.slice(0, -1), turn] : [...prev, turn];
    });
  }, []);

  const onBotOutput = useCallback((d: BotOutputData) => {
    if (d.will_be_spoken === false) return;
    const progress = d.spoken_progress;
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      const turn = last?.role === 'bot' ? { ...last, segments: [...last.segments] } : null;
      const segId = d.segment_id ?? -nextId.current++;
      const existing = turn?.segments.findIndex((s) => s.id === segId) ?? -1;

      if (turn && existing >= 0) {
        // Progress update: how much of this sentence has actually been spoken.
        const seg = { ...turn.segments[existing] };
        if (progress) {
          seg.spoken = progress.accumulated_text;
          if (progress.accumulated_text.length + progress.remaining_text.length > seg.text.length)
            seg.text = progress.accumulated_text + progress.remaining_text;
        } else {
          seg.spoken = seg.text;
        }
        if (d.spoken_status === 'completed') seg.spoken = seg.text;
        turn.segments[existing] = seg;
        return [...prev.slice(0, -1), turn];
      }

      const text = progress ? progress.accumulated_text + progress.remaining_text || d.text : d.text;
      const seg = {
        id: segId,
        text,
        spoken: d.spoken_status === 'completed' || !progress ? text : progress.accumulated_text,
      };
      if (turn) {
        turn.segments.push(seg);
        return [...prev.slice(0, -1), turn];
      }
      return [...prev, { id: nextId.current++, role: 'bot', segments: [seg] }];
    });
  }, []);

  const onServerMessage = useCallback((msg: ServerEvent) => {
    if (msg.type === 'tool_started') setActivity(TOOL_LABEL[msg.tool] ?? 'Working');
    if (msg.type === 'availability_checked') setActivity(null);
    if (msg.type === 'appointment_booked' || msg.type === 'appointment_cancelled') {
      setActivity(null);
      sounds.success();
      // The card sits in the transcript, right where it happened.
      setTurns((t) => [
        ...t,
        {
          id: nextId.current++,
          role: 'card',
          kind: msg.type === 'appointment_booked' ? 'booked' : 'cancelled',
          appointment: msg.appointment,
        },
      ]);
    }
  }, []);

  // --------------------------------------------------------------- control

  const finish = useCallback((reason?: string) => {
    sounds.stopRing();
    if (statusRef.current === 'ended' || statusRef.current === 'error' || statusRef.current === 'idle') return;
    if (reason) {
      setError(reason);
      setStat('error');
    } else {
      setStat('ended');
    }
    setEndedAt(Date.now());
    setActivity(null);
    setSpeaker(null);
    sounds.hangup();
  }, []);

  const start = useCallback(async () => {
    if (statusRef.current === 'ringing' || statusRef.current === 'connected') return;
    setTurns([]);
    setError(null);
    setMuted(false);
    setStartedAt(null);
    setEndedAt(null);
    setActivity(null);
    setStat('ringing');
    sounds.startRing();
    const ringStarted = Date.now();

    const pc = new PipecatClient({
      transport: new SmallWebRTCTransport(),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTrackStarted: (track, participant) => {
          // SmallWebRTC reports the bot's track without a participant, so play any audio
          // track that isn't our own microphone.
          if (track.kind === 'audio' && participant?.local !== true && audioEl.current) {
            audioEl.current.srcObject = new MediaStream([track]);
            void audioEl.current.play().catch(() => {});
          }
        },
        onUserTranscript,
        onBotOutput,
        onServerMessage,
        onLocalAudioLevel: (l) => (levels.current.user = l),
        onRemoteAudioLevel: (l) => (levels.current.bot = l),
        onUserStartedSpeaking: () => setSpeaker('user'),
        onUserStoppedSpeaking: () => setSpeaker((s) => (s === 'user' ? null : s)),
        onBotStartedSpeaking: () => setSpeaker('bot'),
        onBotStoppedSpeaking: () => setSpeaker((s) => (s === 'bot' ? null : s)),
        onDisconnected: () => finish(),
        onError: (m) => console.warn('RTVI error', m),
      },
    });
    client.current = pc;

    try {
      await pc.connect({ webrtcRequestParams: { endpoint: api.offerUrl } });
      const wait = MIN_RING_MS - (Date.now() - ringStarted);
      if (wait > 0) await new Promise((r) => setTimeout(r, wait));
      if ((statusRef.current as CallStatus) !== 'ringing') return; // user hung up while ringing
      sounds.stopRing();
      sounds.connected();
      setStartedAt(Date.now());
      setStat('connected');
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      finish(
        /permission|NotAllowed/i.test(msg)
          ? 'Microphone access was blocked. Allow it in the browser and try again.'
          : 'Couldn’t reach the agent. Check that the server is running.',
      );
      void pc.disconnect().catch(() => {});
    }
  }, [finish, onBotOutput, onServerMessage, onUserTranscript]);

  const end = useCallback(async () => {
    finish();
    const pc = client.current;
    client.current = null;
    if (pc) await pc.disconnect().catch(() => {});
  }, [finish]);

  const toggleMute = useCallback(() => {
    const pc = client.current;
    if (!pc) return;
    const next = !muted;
    pc.enableMic(!next);
    setMuted(next);
  }, [muted]);

  const dismiss = useCallback(() => setStat('idle'), []);

  useEffect(() => () => void client.current?.disconnect(), []);

  return {
    status,
    error,
    muted,
    startedAt,
    endedAt,
    turns,
    activity,
    speaker,
    levels,
    audioEl,
    start,
    end,
    toggleMute,
    dismiss,
  };
}

export type CallApi = ReturnType<typeof useCall>;
// Call sounds made with the Web Audio API, so there are no audio files to ship.

let ctx: AudioContext | null = null;
const audio = () => (ctx ??= new AudioContext());

function tone(freqs: number[], start: number, length: number, gain = 0.06) {
  const ac = audio();
  const g = ac.createGain();
  g.gain.setValueAtTime(0, start);
  g.gain.linearRampToValueAtTime(gain, start + 0.02);
  g.gain.setValueAtTime(gain, start + length - 0.03);
  g.gain.linearRampToValueAtTime(0, start + length);
  g.connect(ac.destination);
  for (const f of freqs) {
    const o = ac.createOscillator();
    o.frequency.value = f;
    o.connect(g);
    o.start(start);
    o.stop(start + length);
  }
}

let ringTimer: number | undefined;

/** Indian-style ringback: two short 400/450 Hz bursts, then a pause. */
export function startRing() {
  stopRing();
  const ring = () => {
    const t = audio().currentTime + 0.05;
    tone([400, 450], t, 0.4);
    tone([400, 450], t + 0.6, 0.4);
  };
  void audio().resume();
  ring();
  ringTimer = window.setInterval(ring, 3000);
}

export function stopRing() {
  if (ringTimer) window.clearInterval(ringTimer);
  ringTimer = undefined;
}

/** Soft rising chime when the agent picks up. */
export function connected() {
  const t = audio().currentTime + 0.02;
  tone([660], t, 0.09, 0.05);
  tone([880], t + 0.1, 0.14, 0.05);
}

/** Three falling beeps when the call ends. */
export function hangup() {
  const t = audio().currentTime + 0.02;
  [620, 520, 420].forEach((f, i) => tone([f], t + i * 0.16, 0.12, 0.05));
}

/** Small confirmation blip for a booking. */
export function success() {
  const t = audio().currentTime + 0.02;
  tone([784, 1175], t, 0.18, 0.035);
}

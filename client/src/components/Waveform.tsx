import { useEffect, useRef, type MutableRefObject } from 'react';

type Props = {
  levels: MutableRefObject<{ user: number; bot: number }>;
  active: boolean;
};

const BARS = 36;

/**
 * Rolling audio meter. Each frame we push the louder of (caller, agent)
 * and draw the history as mirrored bars: warm for the agent, light for the caller.
 */
export function Waveform({ levels, active }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const ctx = el.getContext('2d')!;
    const history: { v: number; who: 'user' | 'bot' }[] = Array.from({ length: BARS }, () => ({ v: 0, who: 'bot' }));
    let raf = 0;
    let frame = 0;

    const draw = () => {
      raf = requestAnimationFrame(draw);
      const dpr = window.devicePixelRatio || 1;
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (el.width !== w * dpr) {
        el.width = w * dpr;
        el.height = h * dpr;
      }
      // Sample every other frame so the motion reads as speech, not jitter.
      if (frame++ % 2 === 0) {
        const { user, bot } = levels.current;
        const who = bot > user ? 'bot' : 'user';
        const raw = active ? Math.max(user, bot) : 0;
        const v = Math.min(1, Math.pow(raw, 0.6) * 1.6);
        history.push({ v, who });
        history.shift();
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const gap = 3;
      const bw = (w - gap * (BARS - 1)) / BARS;
      history.forEach(({ v, who }, i) => {
        const idle = 0.06 + 0.04 * Math.sin((Date.now() / 600) + i * 0.5);
        const bh = Math.max(3, (active ? Math.max(v, idle * 0.6) : idle) * h);
        ctx.fillStyle = who === 'bot' && v > 0.05 ? '#E8A33D' : 'rgba(244,241,234,0.75)';
        ctx.globalAlpha = 0.35 + 0.65 * (i / BARS);
        const x = i * (bw + gap);
        const y = (h - bh) / 2;
        ctx.beginPath();
        ctx.roundRect(x, y, bw, bh, bw / 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1;
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [levels, active]);

  return <canvas ref={canvas} className="waveform" aria-hidden />;
}

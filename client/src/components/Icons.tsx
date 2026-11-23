// Hand-drawn 24px stroke icons, so we don't pull in an icon library for six glyphs.
type P = { size?: number };
const base = (size = 20) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
});

export const PhoneIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M5 4h3l2 5-2.5 1.5a11 11 0 0 0 6 6L15 14l5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />
  </svg>
);
export const HangUpIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M3 14.5c5-4.7 13-4.7 18 0l-2.2 2.6-3.6-1.4v-2.5a11 11 0 0 0-6.4 0v2.5l-3.6 1.4z" fill="currentColor" stroke="none" />
  </svg>
);
export const MicIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);
export const MicOffIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M15 9.3V6a3 3 0 0 0-5.7-1.3M9 9v2a3 3 0 0 0 4.6 2.5M5 11a7 7 0 0 0 11.2 5.6M19 11a7 7 0 0 1-.6 2.8M12 18v3M3 3l18 18" />
  </svg>
);
export const CheckIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </svg>
);
export const XIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);
export const ResetIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" />
  </svg>
);

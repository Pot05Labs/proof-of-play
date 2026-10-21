export function Wordmark({ size = 20 }: { size?: number }) {
  return (
    <span className="wordmark" style={{ fontSize: size }}>
      <svg width={size * 1.3} height={size} viewBox="0 0 26 20" aria-hidden="true">
        <rect x="1" y="1" width="24" height="18" rx="1" fill="none" stroke="#ffc247" strokeWidth="2" />
        <line x1="13" y1="1" x2="13" y2="19" stroke="#ffc247" strokeWidth="2" />
        <circle cx="13" cy="10" r="2.6" fill="#ffc247" />
      </svg>
      Proof of Play
    </span>
  );
}

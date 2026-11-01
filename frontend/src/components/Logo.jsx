export default function Logo({ size = 36, withWordmark = true, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        role="img"
        aria-label="ThreatLens logo"
      >
        <defs>
          <linearGradient id="tl-lens-grad" x1="8" y1="6" x2="40" y2="42" gradientUnits="userSpaceOnUse">
            <stop stopColor="#7EE7E1" />
            <stop offset="1" stopColor="#0F958F" />
          </linearGradient>
        </defs>
        <path
          d="M24 3.5 40 9.6v12.2c0 9.9-6.4 18.4-16 22.7-9.6-4.3-16-12.8-16-22.7V9.6L24 3.5Z"
          stroke="url(#tl-lens-grad)"
          strokeWidth="2.2"
        />
        <circle cx="23" cy="23" r="7.2" stroke="url(#tl-lens-grad)" strokeWidth="2.2" />
        <path d="m28.6 28.6 5.4 5.4" stroke="url(#tl-lens-grad)" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="23" cy="23" r="2.1" fill="#7EE7E1" />
      </svg>
      {withWordmark && (
        <span className="flex flex-col leading-none">
          <span className="text-[17px] font-bold tracking-tight text-[var(--text)]">
            Threat<span className="accent">Lens</span>
          </span>
          <span className="mt-1 text-[9px] font-semibold uppercase tracking-[0.22em] text-faint">
            Threat analysis
          </span>
        </span>
      )}
    </span>
  );
}

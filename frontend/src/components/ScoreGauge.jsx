import { classificationMeta, clampScore } from "../lib/format";

export default function ScoreGauge({ score, classification, size = 190, label = "Risk score" }) {
  const value = clampScore(score);
  const meta = classificationMeta(classification);
  const radius = 72;
  const circumference = Math.PI * radius;
  const offset = circumference * (1 - value / 100);

  return (
    <div className="relative inline-flex flex-col items-center" style={{ width: size }}>
      <svg width={size} height={size * 0.68} viewBox="0 0 180 124" aria-hidden="true">
        <defs>
          <linearGradient id={`gauge-${classification || "x"}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--safe)" />
            <stop offset="52%" stopColor="var(--warn)" />
            <stop offset="100%" stopColor="var(--danger)" />
          </linearGradient>
        </defs>
        <path
          d="M18 110 A72 72 0 0 1 162 110"
          fill="none"
          stroke="var(--border)"
          strokeWidth="13"
          strokeLinecap="round"
        />
        <path
          d="M18 110 A72 72 0 0 1 162 110"
          fill="none"
          stroke={`url(#gauge-${classification || "x"})`}
          strokeWidth="13"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.22,1,0.36,1)" }}
        />
        <text
          x="90"
          y="94"
          textAnchor="middle"
          fontSize="36"
          fontWeight="700"
          fill="var(--text)"
          fontFamily="Inter, system-ui, sans-serif"
        >
          {value}
        </text>
        <text
          x="90"
          y="113"
          textAnchor="middle"
          fontSize="9"
          letterSpacing="2.4"
          fill="var(--faint)"
          fontFamily="Inter, system-ui, sans-serif"
        >
          {label.toUpperCase()}
        </text>
      </svg>
      <div
        className="-mt-1 inline-flex items-center gap-1.5 text-xs font-semibold"
        style={{ color: meta.color }}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />
        {meta.label}
      </div>
    </div>
  );
}

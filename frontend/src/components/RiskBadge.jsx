import { ShieldAlert, ShieldCheck, ShieldQuestion, TriangleAlert } from "lucide-react";
import { classificationMeta } from "../lib/format";

const ICONS = {
  malicious: ShieldAlert,
  suspicious: TriangleAlert,
  no_significant_indicators: ShieldCheck,
  unknown: ShieldQuestion,
};

export default function RiskBadge({ classification, size = "md", showIcon = true }) {
  const meta = classificationMeta(classification);
  const Icon = ICONS[classification] || ShieldQuestion;
  const padding = size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-semibold tracking-wide ${padding}`}
      style={{
        color: meta.color,
        borderColor: `color-mix(in srgb, ${meta.color} 38%, transparent)`,
        background: `color-mix(in srgb, ${meta.color} 10%, transparent)`,
      }}
      title={meta.description}
    >
      {showIcon && <Icon size={size === "sm" ? 11 : 13} />}
      {meta.label}
    </span>
  );
}

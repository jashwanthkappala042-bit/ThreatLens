export const CLASSIFICATION = {
  malicious: {
    label: "High risk",
    short: "High risk",
    tone: "danger",
    color: "var(--danger)",
    description: "Strong indicators support treating this as dangerous.",
  },
  suspicious: {
    label: "Suspicious",
    short: "Suspicious",
    tone: "warn",
    color: "var(--warn)",
    description: "Some indicators warrant caution and verification.",
  },
  no_significant_indicators: {
    label: "No significant indicators",
    short: "Low signal",
    tone: "safe",
    color: "var(--safe)",
    description: "No significant indicators in completed stages. Not a guarantee.",
  },
  unknown: {
    label: "Inconclusive",
    short: "Unknown",
    tone: "unknown",
    color: "var(--faint)",
    description: "The evidence is insufficient for a reliable assessment.",
  },
};

export function classificationMeta(value) {
  return (
    CLASSIFICATION[value] || {
      label: value || "Unknown",
      short: "Unknown",
      tone: "unknown",
      color: "var(--faint)",
      description: "No assessment is available.",
    }
  );
}

export const SEVERITY = {
  critical: { label: "Critical", color: "var(--danger)" },
  high: { label: "High", color: "#ff8c69" },
  medium: { label: "Medium", color: "var(--warn)" },
  low: { label: "Low", color: "var(--accent)" },
  info: { label: "Info", color: "var(--faint)" },
};

export function severityMeta(value) {
  return SEVERITY[value] || SEVERITY.info;
}

export function formatDate(value, { withTime = true } = {}) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function relativeTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diff = Date.now() - date.getTime();
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return "just now";
  if (diff < hour) return `${Math.floor(diff / minute)}m ago`;
  if (diff < day) return `${Math.floor(diff / hour)}h ago`;
  if (diff < 7 * day) return `${Math.floor(diff / day)}d ago`;
  return formatDate(value, { withTime: false });
}

export function inputTypeLabel(type) {
  return { url: "URL", email: "Message", image: "Image" }[type] || type;
}

export function titleCase(value) {
  if (!value) return "";
  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function clampScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, Math.round(number)));
}

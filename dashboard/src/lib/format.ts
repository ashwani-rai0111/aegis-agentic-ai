export function formatTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export function shortId(id: string) {
  return id.slice(0, 8);
}

export function confidenceLabel(value: number | null | undefined) {
  if (value == null) return "—";
  // Models sometimes return 0–100; normalize to a percentage display.
  const normalized = value > 1 ? value / 100 : value;
  const pct = Math.round(Math.min(Math.max(normalized, 0), 1) * 100);
  return `${pct}%`;
}

export function statusTone(status: string) {
  switch (status) {
    case "RECOVERED":
      return "mint";
    case "FAILED":
    case "ESCALATED":
      return "rose";
    case "AWAITING_APPROVAL":
    case "EXECUTING":
    case "VERIFYING":
      return "amber";
    default:
      return "sky";
  }
}

/** Agent still working — show loader until a terminal / waiting-for-human status. */
export function isStatusInProgress(status: string) {
  return ![
    "RECOVERED",
    "FAILED",
    "ESCALATED",
    "AWAITING_APPROVAL",
  ].includes(status);
}

export function severityTone(severity: string) {
  switch (severity) {
    case "CRITICAL":
    case "HIGH":
      return "rose";
    case "MEDIUM":
      return "amber";
    default:
      return "sky";
  }
}
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
  return `${Math.round(value * 100)}%`;
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
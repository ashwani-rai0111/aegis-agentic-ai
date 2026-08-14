import { isStatusInProgress, severityTone, statusTone } from "@/lib/format";

const toneClass: Record<string, string> = {
  mint: "bg-signal-mint/15 text-signal-mint border-signal-mint/30",
  rose: "bg-signal-rose/15 text-signal-rose border-signal-rose/30",
  amber: "bg-signal-amber/15 text-signal-amber border-signal-amber/30",
  sky: "bg-signal-sky/15 text-signal-sky border-signal-sky/30",
};

function StatusSpinner() {
  return (
    <span
      className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent opacity-80"
      aria-hidden
    />
  );
}

export function StatusBadge({ status }: { status: string }) {
  const busy = isStatusInProgress(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono text-[11px] tracking-wide ${toneClass[statusTone(status)]}`}
    >
      {busy ? <StatusSpinner /> : null}
      {status}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[11px] tracking-wide ${toneClass[severityTone(severity)]}`}
    >
      {severity}
    </span>
  );
}

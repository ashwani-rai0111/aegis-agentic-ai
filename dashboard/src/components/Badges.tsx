import { severityTone, statusTone } from "@/lib/format";

const toneClass: Record<string, string> = {
  mint: "bg-signal-mint/15 text-signal-mint border-signal-mint/30",
  rose: "bg-signal-rose/15 text-signal-rose border-signal-rose/30",
  amber: "bg-signal-amber/15 text-signal-amber border-signal-amber/30",
  sky: "bg-signal-sky/15 text-signal-sky border-signal-sky/30",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[11px] tracking-wide ${toneClass[statusTone(status)]}`}
    >
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
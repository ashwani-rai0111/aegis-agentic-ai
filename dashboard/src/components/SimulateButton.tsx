"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { simulateIncident } from "@/lib/api";

const SCENARIOS = [
  {
    id: "api_memory_pressure",
    label: "Simulate API memory pressure",
    hint: "Auto low-risk PM2 restart",
  },
  {
    id: "mysql_restart_required",
    label: "Simulate MySQL failure",
    hint: "Needs human approval",
  },
] as const;

export function SimulateButton({ onDone }: { onDone?: () => void }) {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(scenario: string) {
    setLoading(scenario);
    setError(null);
    try {
      const incident = await simulateIncident({ scenario });
      onDone?.();
      router.push(`/incidents/${incident.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <div className="flex flex-wrap gap-2">
        {SCENARIOS.map((scenario) => (
          <button
            key={scenario.id}
            type="button"
            onClick={() => run(scenario.id)}
            disabled={loading !== null}
            className="rounded-lg bg-signal-amber px-4 py-2.5 font-mono text-sm font-semibold tracking-wide text-ink-950 transition hover:brightness-110 disabled:cursor-wait disabled:opacity-70"
            title={scenario.hint}
          >
            {loading === scenario.id ? "Running agent loop…" : scenario.label}
          </button>
        ))}
      </div>
      <p className="font-mono text-[11px] text-mist-400">
        Memory pressure auto-remediates · MySQL path pauses for approval
      </p>
      {error ? (
        <p className="max-w-md font-mono text-xs text-signal-rose">{error}</p>
      ) : null}
    </div>
  );
}

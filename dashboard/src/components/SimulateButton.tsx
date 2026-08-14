"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { runLiveIncident, simulateIncident } from "@/lib/api";

const SCENARIOS = [
  {
    id: "api_memory_pressure",
    label: "Simulate API memory pressure",
    hint: "Mock · auto low-risk PM2 restart",
  },
  {
    id: "mysql_restart_required",
    label: "Simulate MySQL failure",
    hint: "Mock · needs human approval",
  },
] as const;

export function SimulateButton({
  onDone,
  onRunStart,
  onRunSaved,
  onRunFailed,
}: {
  onDone?: () => void | Promise<void>;
  onRunStart?: () => void;
  onRunSaved?: (id: string) => void | Promise<void>;
  onRunFailed?: () => void;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runMock(scenario: string) {
    if (loading !== null) return;
    setLoading(scenario);
    setError(null);
    onRunStart?.();
    try {
      const incident = await simulateIncident({ scenario });
      await onRunSaved?.(incident.id);
      await onDone?.();
      router.push(`/incidents/${incident.id}`);
    } catch (err) {
      onRunFailed?.();
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setLoading(null);
    }
  }

  async function runLive() {
    if (loading !== null) return;
    setLoading("live_aws");
    setError(null);
    onRunStart?.();
    try {
      const incident = await runLiveIncident();
      await onRunSaved?.(incident.id);
      await onDone?.();
      router.push(`/incidents/${incident.id}`);
    } catch (err) {
      onRunFailed?.();
      setError(err instanceof Error ? err.message : "Live AWS run failed");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex flex-col items-stretch gap-2 sm:items-end">
      <div className="flex flex-wrap gap-2">
        {/* Simulate buttons temporarily disabled — using live AWS only
        {SCENARIOS.map((scenario) => (
          <button
            key={scenario.id}
            type="button"
            onClick={() => runMock(scenario.id)}
            disabled={loading !== null}
            className="rounded-lg bg-signal-amber px-4 py-2.5 font-mono text-sm font-semibold tracking-wide text-ink-950 transition hover:brightness-110 disabled:cursor-wait disabled:opacity-70"
            title={scenario.hint}
          >
            {loading === scenario.id ? "Running agent loop…" : scenario.label}
          </button>
        ))}
        */}
        <button
          type="button"
          onClick={runLive}
          disabled={loading !== null}
          className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-signal-amber px-5 py-3 font-mono text-sm font-semibold tracking-wide text-ink-950 shadow-[0_8px_24px_rgba(232,162,58,0.28)] transition hover:brightness-110 hover:shadow-[0_10px_28px_rgba(232,162,58,0.38)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber/70 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 active:translate-y-px disabled:cursor-wait disabled:opacity-70"
        >
          {loading === "live_aws" ? (
            <>
              <span
                className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-950/30 border-t-ink-950"
                aria-hidden
              />
              Running on AWS…
            </>
          ) : (
            <>
              Run against live AWS
            </>
          )}
        </button>
      </div>
      <p className="font-mono text-[11px] text-mist-400">
        CloudWatch · EC2 · SSM
      </p>
      {error ? (
        <p className="max-w-xl font-mono text-xs text-signal-rose">{error}</p>
      ) : null}
    </div>
  );
}

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
    <div className="flex flex-col items-start gap-3">
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
          className="rounded-lg border border-signal-sky/60 bg-ink-950/40 px-4 py-2.5 font-mono text-sm font-semibold tracking-wide text-signal-sky transition hover:bg-ink-950/70 disabled:cursor-wait disabled:opacity-70"
          title="Requires AEGIS_TOOL_BACKEND=aws and credentials in .env"
        >
          {loading === "live_aws" ? "Running on AWS…" : "Run against live AWS"}
        </button>
      </div>
      <p className="font-mono text-[11px] text-mist-400">
        Live AWS · CloudWatch + EC2 + SSM
      </p>
      {error ? (
        <p className="max-w-xl font-mono text-xs text-signal-rose">{error}</p>
      ) : null}
    </div>
  );
}

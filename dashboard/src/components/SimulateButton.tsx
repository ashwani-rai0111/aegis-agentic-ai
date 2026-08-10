"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { simulateIncident } from "@/lib/api";

export function SimulateButton({ onDone }: { onDone?: () => void }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const incident = await simulateIncident();
      onDone?.();
      router.push(`/incidents/${incident.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={run}
        disabled={loading}
        className="rounded-lg bg-signal-amber px-4 py-2.5 font-mono text-sm font-semibold tracking-wide text-ink-950 transition hover:brightness-110 disabled:cursor-wait disabled:opacity-70"
      >
        {loading ? "Running agent loop…" : "Simulate incident"}
      </button>
      {error ? (
        <p className="max-w-md font-mono text-xs text-signal-rose">{error}</p>
      ) : null}
    </div>
  );
}
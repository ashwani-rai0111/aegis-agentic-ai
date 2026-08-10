"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchIncidents } from "@/lib/api";
import { confidenceLabel, formatTime, shortId } from "@/lib/format";
import type { IncidentSummary } from "@/lib/types";
import { SeverityBadge, StatusBadge } from "./Badges";
import { SimulateButton } from "./SimulateButton";

export function IncidentList() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await fetchIncidents();
      setIncidents(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [load]);

  const stats = useMemo(() => {
    const recovered = incidents.filter((i) => i.status === "RECOVERED").length;
    const open = incidents.filter(
      (i) => !["RECOVERED", "FAILED", "ESCALATED"].includes(i.status),
    ).length;
    return { total: incidents.length, recovered, open };
  }, [incidents]);

  return (
    <div className="space-y-8 animate-fade-up">
      <section className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <p className="label">Live operations</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight text-mist-50 sm:text-5xl">
            Incident console
          </h1>
          <p className="text-base leading-relaxed text-mist-300">
            Watch Aegis investigate, decide, act, and verify. Simulate a mock
            CloudWatch incident to run the full agent loop.
          </p>
        </div>
        <SimulateButton onDone={load} />
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        {[
          { label: "Total", value: stats.total },
          { label: "Open", value: stats.open },
          { label: "Recovered", value: stats.recovered },
        ].map((item, index) => (
          <div
            key={item.label}
            className="panel px-4 py-3"
            style={{ animationDelay: `${index * 60}ms` }}
          >
            <p className="label">{item.label}</p>
            <p className="mt-1 font-display text-3xl text-mist-50">{item.value}</p>
          </div>
        ))}
      </section>

      <section className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-mist-300/10 px-4 py-3">
          <h2 className="font-display text-lg text-mist-50">Incidents</h2>
          <button
            type="button"
            onClick={load}
            className="font-mono text-xs text-signal-sky hover:underline"
          >
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="px-4 py-8 font-mono text-sm text-mist-400">Loading…</p>
        ) : error ? (
          <p className="px-4 py-8 font-mono text-sm text-signal-rose">{error}</p>
        ) : incidents.length === 0 ? (
          <p className="px-4 py-8 text-sm text-mist-300">
            No incidents yet. Run a simulation to create the first timeline.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-mist-300/10 font-mono text-[11px] uppercase tracking-wider text-mist-400">
                <tr>
                  <th className="px-4 py-3 font-medium">ID</th>
                  <th className="px-4 py-3 font-medium">Service</th>
                  <th className="px-4 py-3 font-medium">Severity</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Root cause</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                  <th className="px-4 py-3 font-medium">Detected</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((incident) => (
                  <tr
                    key={incident.id}
                    className="border-b border-mist-300/5 transition hover:bg-white/5"
                  >
                    <td className="px-4 py-3 font-mono text-signal-sky">
                      <Link href={`/incidents/${incident.id}`} className="hover:underline">
                        {shortId(incident.id)}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{incident.service}</td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={incident.severity} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={incident.status} />
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 text-mist-300">
                      {incident.root_cause || "—"}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {confidenceLabel(incident.confidence)}
                    </td>
                    <td className="px-4 py-3 font-mono text-mist-400">
                      {formatTime(incident.detected_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
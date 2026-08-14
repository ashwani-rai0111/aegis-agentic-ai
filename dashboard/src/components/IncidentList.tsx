"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchIncidents } from "@/lib/api";
import { confidenceLabel, formatTime, shortId } from "@/lib/format";
import type { IncidentSummary } from "@/lib/types";
import { SeverityBadge, StatusBadge } from "./Badges";
import { InvestigateBox } from "./InvestigateBox";
import { SimulateButton } from "./SimulateButton";

export function IncidentList() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const knownIdsRef = useRef<Set<string>>(new Set());
  const incidentsRef = useRef<IncidentSummary[]>([]);

  const load = useCallback(async () => {
    try {
      const data = await fetchIncidents();
      setIncidents(data);
      incidentsRef.current = data;
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const ms = pending ? 2000 : 8000;
    const id = setInterval(load, ms);
    return () => clearInterval(id);
  }, [load, pending]);

  const newSavedRow = incidents.find((incident) => !knownIdsRef.current.has(incident.id));
  const showPending = pending && !newSavedRow;

  useEffect(() => {
    if (pending && newSavedRow) setPending(false);
  }, [pending, newSavedRow]);

  const stats = useMemo(() => {
    const recovered = incidents.filter((i) => i.status === "RECOVERED").length;
    const open = incidents.filter(
      (i) => !["RECOVERED", "FAILED", "ESCALATED"].includes(i.status),
    ).length;
    return {
      total: incidents.length + (showPending ? 1 : 0),
      recovered,
      open: open + (showPending ? 1 : 0),
    };
  }, [incidents, showPending]);

  const runHandlers = {
    onRunStart: () => {
      knownIdsRef.current = new Set(incidentsRef.current.map((incident) => incident.id));
      setPending(true);
    },
    onRunSaved: async () => {
      await load();
    },
    onRunFailed: () => {
      setPending(false);
    },
  };

  return (
    <div className="space-y-8 animate-fade-up">
      <section className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <p className="label">Live operations</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight text-mist-50 sm:text-5xl">
            Incident console
          </h1>
          <p className="text-base leading-relaxed text-mist-300">
            Describe a real issue (e.g. Signyn website down) or run against live
            AWS. Aegis investigates, decides, acts, and verifies.
          </p>
        </div>
        <SimulateButton onDone={load} {...runHandlers} />
      </section>

      <section className="animate-fade-up">
        <InvestigateBox onDone={load} {...runHandlers} />
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
        ) : incidents.length === 0 && !showPending ? (
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
                {showPending ? (
                  <tr className="border-b border-mist-300/5 bg-signal-sky/5">
                    <td className="px-4 py-3 font-mono text-mist-400">pending</td>
                    <td className="px-4 py-3 text-mist-300">signyn</td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity="HIGH" />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status="INVESTIGATING" />
                    </td>
                    <td className="px-4 py-3 text-mist-400">Working…</td>
                    <td className="px-4 py-3 font-mono text-mist-400">—</td>
                    <td className="px-4 py-3 font-mono text-mist-400">now</td>
                  </tr>
                ) : null}
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

"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { approveIncident, fetchIncident, rejectIncident } from "@/lib/api";
import { confidenceLabel, formatTime, shortId } from "@/lib/format";
import type { IncidentDetail } from "@/lib/types";
import { SeverityBadge, StatusBadge } from "./Badges";

export function IncidentDetailView({ incidentId }: { incidentId: string }) {
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchIncident(incidentId);
      setIncident(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incident");
    }
  }, [incidentId]);

  useEffect(() => {
    load();
  }, [load]);

  const timeline = useMemo(() => {
    if (!incident) return [];
    return [...incident.audit_logs].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
  }, [incident]);

  const plan = incident?.plans?.length
    ? incident.plans[incident.plans.length - 1]
    : undefined;
  const visibleHypotheses = useMemo(() => {
    const placeholders = new Set([
      "unknown",
      "n/a",
      "na",
      "none",
      "null",
      "-",
      "tbd",
    ]);
    return (incident?.hypotheses ?? [])
      .filter((hyp) => {
        const label = (hyp.hypothesis || "").trim().toLowerCase();
        return label.length >= 8 && !placeholders.has(label);
      })
      .slice()
      .sort((a, b) => b.score - a.score);
  }, [incident]);
  const selectedHypotheses = visibleHypotheses.filter((h) => h.selected);

  async function onApprove() {
    setApproving(true);
    try {
      const updated = await approveIncident(incidentId);
      setIncident(updated);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval failed");
    } finally {
      setApproving(false);
    }
  }

  async function onReject() {
    setRejecting(true);
    try {
      const updated = await rejectIncident(incidentId);
      setIncident(updated);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setRejecting(false);
    }
  }

  if (error && !incident) {
    return (
      <div className="panel p-6">
        <p className="font-mono text-signal-rose">{error}</p>
        <Link href="/" className="mt-4 inline-block text-signal-sky hover:underline">
          Back to console
        </Link>
      </div>
    );
  }

  if (!incident) {
    return <p className="font-mono text-mist-400">Loading incident…</p>;
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/" className="font-mono text-xs text-signal-sky hover:underline">
          ← All incidents
        </Link>
        <button
          type="button"
          onClick={load}
          className="font-mono text-xs text-mist-300 hover:text-mist-50"
        >
          Refresh
        </button>
      </div>

      <section className="panel p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <p className="label">Incident {shortId(incident.id)}</p>
            <h1 className="font-display text-3xl font-semibold text-mist-50 sm:text-4xl">
              {incident.service}
            </h1>
            <p className="max-w-3xl text-mist-300">
              {incident.summary || "Agent investigation in progress."}
            </p>
            <div className="flex flex-wrap gap-2">
              <StatusBadge status={incident.status} />
              <SeverityBadge severity={incident.severity} />
              <span className="rounded-md border border-mist-300/20 px-2 py-0.5 font-mono text-[11px] text-mist-300">
                mode {incident.agent_mode || "—"}
              </span>
              <span className="rounded-md border border-mist-300/20 px-2 py-0.5 font-mono text-[11px] text-mist-300">
                {incident.scenario}
              </span>
            </div>
          </div>
          <div className="min-w-[180px] rounded-lg border border-mist-300/15 bg-ink-950/40 p-4">
            <p className="label">Confidence</p>
            <p className="mt-1 font-display text-3xl text-signal-amber">
              {confidenceLabel(incident.confidence)}
            </p>
            <p className="mt-3 label">Detected</p>
            <p className="font-mono text-xs text-mist-300">
              {formatTime(incident.detected_at)}
            </p>
          </div>
        </div>

        {incident.root_cause ? (
          <div className="mt-5 rounded-lg border border-signal-amber/20 bg-signal-amber/5 p-4">
            <p className="label">Root cause</p>
            <p className="mt-1 text-mist-50">{incident.root_cause}</p>
          </div>
        ) : null}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="panel p-5">
          <h2 className="font-display text-xl text-mist-50">Timeline</h2>
          <ol className="mt-4 space-y-3">
            {timeline.length === 0 ? (
              <li className="text-sm text-mist-400">No audit events yet.</li>
            ) : (
              timeline.map((event) => (
                <li
                  key={event.id}
                  className="relative border-l border-signal-sky/30 pl-4"
                >
                  <span className="absolute -left-1 top-1.5 h-2 w-2 rounded-full bg-signal-sky" />
                  <p className="font-mono text-[11px] text-mist-400">
                    {formatTime(event.timestamp)} · {event.actor}
                  </p>
                  <p className="text-sm text-mist-50">{event.action}</p>
                  {event.result ? (
                    <p className="mt-0.5 font-mono text-xs text-mist-300">
                      {event.result}
                    </p>
                  ) : null}
                </li>
              ))
            )}
          </ol>
        </section>

        <section className="panel p-5">
          <h2 className="font-display text-xl text-mist-50">Evidence</h2>
          <div className="mt-4 max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {incident.observations.length === 0 ? (
              <p className="text-sm text-mist-400">No observations recorded.</p>
            ) : (
              incident.observations.map((obs) => (
                <div
                  key={obs.id}
                  className="rounded-lg border border-mist-300/10 bg-ink-950/35 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-mono text-[11px] uppercase tracking-wide text-signal-sky">
                      {obs.source} · {obs.name}
                    </p>
                    <p className="font-mono text-[10px] text-mist-400">
                      {formatTime(obs.timestamp)}
                    </p>
                  </div>
                  <p className="mt-1 break-words font-mono text-xs text-mist-100">
                    {obs.value.length > 220
                      ? `${obs.value.slice(0, 220)}…`
                      : obs.value}
                  </p>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="panel p-5">
          <h2 className="font-display text-xl text-mist-50">Hypotheses</h2>
          <div className="mt-4 space-y-3">
            {visibleHypotheses.length === 0 ? (
              <p className="text-sm text-mist-400">No hypotheses yet.</p>
            ) : (
              visibleHypotheses.map((hyp) => (
                  <div
                    key={hyp.id}
                    className={`rounded-lg border px-3 py-3 ${
                      hyp.selected
                        ? "border-signal-amber/40 bg-signal-amber/10"
                        : "border-mist-300/10 bg-ink-950/30"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm text-mist-50">{hyp.hypothesis}</p>
                      <span className="font-mono text-xs text-mist-300">
                        {confidenceLabel(hyp.score)}
                      </span>
                    </div>
                    {hyp.evidence_for ? (
                      <p className="mt-2 text-xs text-mist-300">
                        For: {hyp.evidence_for}
                      </p>
                    ) : null}
                    {hyp.evidence_against ? (
                      <p className="mt-1 text-xs text-mist-400">
                        Against: {hyp.evidence_against}
                      </p>
                    ) : null}
                  </div>
                ))
            )}
          </div>
          {selectedHypotheses.length === 0 && visibleHypotheses.length > 0 ? (
            <p className="mt-3 font-mono text-xs text-mist-400">
              No hypothesis marked selected.
            </p>
          ) : null}
        </section>

        <section className="panel p-5">
          <h2 className="font-display text-xl text-mist-50">Plan & action</h2>
          {plan ? (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-mist-300/10 bg-ink-950/30 p-3">
                <p className="label">Proposed action</p>
                <p className="mt-1 font-mono text-sm text-signal-amber">
                  {plan.proposed_action}
                </p>
                <p className="mt-2 text-xs text-mist-300">{plan.rationale}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="rounded border border-mist-300/20 px-2 py-0.5 font-mono text-[11px]">
                    risk {plan.risk}
                  </span>
                  <span className="rounded border border-mist-300/20 px-2 py-0.5 font-mono text-[11px]">
                    {plan.approved ? `approved by ${plan.approved_by}` : "not approved"}
                  </span>
                </div>
                {plan.parameters ? (
                  <pre className="mt-3 overflow-x-auto rounded bg-ink-950/60 p-2 font-mono text-[11px] text-mist-300">
                    {JSON.stringify(plan.parameters, null, 2)}
                  </pre>
                ) : null}
              </div>

              {incident.status === "AWAITING_APPROVAL" ? (
                <div className="space-y-3">
                  <p className="text-sm text-mist-300">
                    Medium/high-risk action paused for human approval. Approving
                    resumes execute → verify automatically.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={onApprove}
                      disabled={approving || rejecting}
                      className="rounded-lg bg-signal-mint px-4 py-2 font-mono text-sm font-semibold text-ink-950 disabled:opacity-60"
                    >
                      {approving ? "Approving…" : "Approve & execute"}
                    </button>
                    <button
                      type="button"
                      onClick={onReject}
                      disabled={approving || rejecting}
                      className="rounded-lg border border-signal-rose/50 px-4 py-2 font-mono text-sm font-semibold text-signal-rose disabled:opacity-60"
                    >
                      {rejecting ? "Rejecting…" : "Reject & escalate"}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="mt-4 text-sm text-mist-400">No plan recorded.</p>
          )}

          <div className="mt-5 space-y-2">
            <p className="label">Actions</p>
            {incident.actions.length === 0 ? (
              <p className="text-sm text-mist-400">No actions executed.</p>
            ) : (
              incident.actions.map((action) => (
                <div
                  key={action.id}
                  className="rounded-lg border border-mist-300/10 bg-ink-950/30 p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-mono text-sm text-mist-50">{action.tool}</p>
                    <span
                      className={`font-mono text-[11px] ${
                        action.success ? "text-signal-mint" : "text-signal-rose"
                      }`}
                    >
                      {action.success ? "SUCCESS" : "FAILED"}
                    </span>
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-mist-400">
                    {formatTime(action.started_at)}
                    {action.approved_by ? ` · ${action.approved_by}` : ""}
                  </p>
                  {action.result ? (
                    <pre className="mt-2 max-h-40 overflow-auto rounded bg-ink-950/60 p-2 font-mono text-[11px] text-mist-300">
                      {action.result}
                    </pre>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <section className="panel p-5">
        <h2 className="font-display text-xl text-mist-50">
          Before / after verification
        </h2>
        {incident.verifications.length === 0 ? (
          <p className="mt-4 text-sm text-mist-400">No verification metrics yet.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="font-mono text-[11px] uppercase tracking-wider text-mist-400">
                <tr>
                  <th className="px-2 py-2">Metric</th>
                  <th className="px-2 py-2">Before</th>
                  <th className="px-2 py-2">After</th>
                  <th className="px-2 py-2">Result</th>
                </tr>
              </thead>
              <tbody>
                {incident.verifications.map((row) => (
                  <tr key={row.id} className="border-t border-mist-300/10">
                    <td className="px-2 py-3 font-mono text-mist-50">{row.metric}</td>
                    <td className="px-2 py-3 font-mono text-mist-300">
                      {row.before_value ?? "—"}
                    </td>
                    <td className="px-2 py-3 font-mono text-mist-300">
                      {row.after_value ?? "—"}
                    </td>
                    <td className="px-2 py-3">
                      <span
                        className={`font-mono text-xs ${
                          row.success ? "text-signal-mint" : "text-signal-rose"
                        }`}
                      >
                        {row.success ? "PASS" : "FAIL"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {error ? <p className="font-mono text-xs text-signal-rose">{error}</p> : null}
    </div>
  );
}
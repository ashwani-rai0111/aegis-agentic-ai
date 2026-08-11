"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchFixJob } from "@/lib/api";
import { formatTime } from "@/lib/format";
import type { FixJob } from "@/lib/types";

export function FixJobDetail({ id }: { id: string }) {
  const [job, setJob] = useState<FixJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchFixJob(id);
      setJob(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load job");
    }
  }, [id]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [load]);

  if (error) {
    return (
      <div className="space-y-4">
        <Link href="/fixes" className="font-mono text-sm text-signal-sky">
          ← Code fixes
        </Link>
        <p className="font-mono text-signal-rose">{error}</p>
      </div>
    );
  }

  if (!job) {
    return <p className="font-mono text-mist-400">Loading…</p>;
  }

  const rows: [string, string | null | undefined][] = [
    ["Status", job.status],
    ["Repo", `${job.repo_key} (${job.profile})`],
    ["URL", job.repo_url],
    ["Backup branch", job.backup_branch],
    ["Fix branch", job.fix_branch],
    ["PR", job.pr_url],
    ["Cursor agent", job.cursor_agent_id],
    ["Cursor run", job.cursor_run_id],
    ["Created", formatTime(job.created_at)],
    ["Completed", job.completed_at ? formatTime(job.completed_at) : "—"],
  ];

  return (
    <div className="space-y-8 animate-fade-up">
      <div className="space-y-3">
        <Link href="/fixes" className="font-mono text-sm text-signal-sky">
          ← Code fixes
        </Link>
        <h1 className="font-display text-3xl font-semibold text-mist-50">
          Fix job
        </h1>
        <p className="font-mono text-xs text-mist-400">{job.id}</p>
      </div>

      <dl className="grid gap-3 rounded-xl border border-mist-300/10 bg-ink-950/40 p-5 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="space-y-1">
            <dt className="label">{label}</dt>
            <dd className="break-all font-mono text-sm text-mist-200">
              {value && String(value).startsWith("http") ? (
                <a
                  href={value}
                  target="_blank"
                  rel="noreferrer"
                  className="text-signal-sky hover:underline"
                >
                  {value}
                </a>
              ) : (
                value || "—"
              )}
            </dd>
          </div>
        ))}
      </dl>

      <section className="space-y-2">
        <p className="label">Reported error</p>
        <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl border border-mist-300/10 bg-ink-950/50 p-4 font-mono text-xs text-mist-200">
          {job.error_text}
        </pre>
      </section>

      {job.notes ? (
        <section className="space-y-2">
          <p className="label">Notes</p>
          <p className="text-sm text-mist-300">{job.notes}</p>
        </section>
      ) : null}

      {job.summary ? (
        <section className="space-y-2">
          <p className="label">Agent summary</p>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl border border-mist-300/10 bg-ink-950/50 p-4 font-mono text-xs text-mist-200">
            {job.summary}
          </pre>
        </section>
      ) : null}

      {job.error ? (
        <section className="space-y-2">
          <p className="label">Error</p>
          <p className="font-mono text-sm text-signal-rose">{job.error}</p>
        </section>
      ) : null}

      {job.profile === "backend_deploy" ? (
        <p className="font-mono text-xs text-mist-400">
          Backend flow: dated backup branch, then fix pushed directly to main.
          Your GitHub → AWS staging deploy runs on that main push.
        </p>
      ) : (
        <p className="font-mono text-xs text-mist-400">
          Frontend profile: GitHub only. No server deploy — store builds stay
          manual.
        </p>
      )}
    </div>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { createFixJob, fetchFixJobs, fetchFixRepos } from "@/lib/api";
import { formatTime, shortId } from "@/lib/format";
import type { FixJob, FixRepo } from "@/lib/types";

function statusClass(status: string) {
  switch (status) {
    case "succeeded":
      return "text-signal-mint";
    case "failed":
      return "text-signal-rose";
    case "running":
      return "text-signal-sky";
    default:
      return "text-signal-amber";
  }
}

export function FixesBoard() {
  const router = useRouter();
  const [repos, setRepos] = useState<FixRepo[]>([]);
  const [jobs, setJobs] = useState<FixJob[]>([]);
  const [repoKey, setRepoKey] = useState("");
  const [errorText, setErrorText] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [fixPassword, setFixPassword] = useState("");

  const load = useCallback(async () => {
    try {
      const [r, j] = await Promise.all([fetchFixRepos(), fetchFixJobs()]);
      setRepos(r);
      setJobs(j);
      setError(null);
      if (!repoKey && r.length) setRepoKey(r[0].key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load fix jobs");
    }
  }, [repoKey]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const selected = repos.find((r) => r.key === repoKey);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!repoKey || errorText.trim().length < 5) return;
    setFixPassword("");
    setError(null);
    setShowPasswordModal(true);
  }

  async function confirmStartFix() {
    if (!fixPassword.trim()) {
      setError("Fix password is required");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const job = await createFixJob({
        repo_key: repoKey,
        error_text: errorText.trim(),
        notes: notes.trim() || undefined,
        fix_password: fixPassword,
      });
      setErrorText("");
      setNotes("");
      setFixPassword("");
      setShowPasswordModal(false);
      await load();
      router.push(`/fixes/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create fix job");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8 animate-fade-up">
      <section className="max-w-2xl space-y-3">
        <p className="label">Code fixes</p>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-mist-50 sm:text-5xl">
          Cursor bug fix
        </h1>
        <p className="text-base leading-relaxed text-mist-300">
          Paste an error for backend or frontend. Configure repos in{" "}
          <span className="font-mono text-mist-200">AEGIS_FIX_REPOS</span> as{" "}
          <span className="font-mono text-mist-200">
            key|url|profile|starting_branch
          </span>
          . Backend uses main + backup + direct push; frontend starts from your branch and
          pushes a new fix branch only.
        </p>
      </section>

      <form
        onSubmit={onSubmit}
        className="space-y-4 rounded-xl border border-mist-300/10 bg-ink-950/40 p-5"
      >
        <div className="space-y-2">
          <label className="label" htmlFor="repo">
            Repository
          </label>
          <select
            id="repo"
            value={repoKey}
            onChange={(e) => setRepoKey(e.target.value)}
            className="w-full rounded-lg border border-mist-300/15 bg-ink-950/50 px-3 py-2 font-mono text-sm text-mist-50 outline-none focus:ring-2 focus:ring-signal-sky/40"
            disabled={loading || repos.length === 0}
          >
            {repos.length === 0 ? (
              <option value="">Configure AEGIS_FIX_REPOS in .env</option>
            ) : (
              repos.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.key} — {r.profile}
                </option>
              ))
            )}
          </select>
          {selected ? (
            <p className="font-mono text-xs text-mist-400">
              start: <span className="text-mist-200">{selected.starting_branch}</span>
              <span className="mx-2 text-mist-600">·</span>
              {selected.deploy_label}
              <span className="mx-2 text-mist-600">·</span>
              <span className="truncate">{selected.url}</span>
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <label className="label" htmlFor="error">
            Error / bug report
          </label>
          <textarea
            id="error"
            value={errorText}
            onChange={(e) => setErrorText(e.target.value)}
            rows={6}
            placeholder="Paste stack traces, failing tests, or describe the bug…"
            className="w-full resize-y rounded-lg border border-mist-300/15 bg-ink-950/50 px-3 py-2 font-mono text-sm text-mist-50 outline-none ring-signal-sky/40 placeholder:text-mist-500 focus:ring-2"
            disabled={loading}
          />
        </div>

        <div className="space-y-2">
          <label className="label" htmlFor="notes">
            Notes (optional)
          </label>
          <input
            id="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. happens on staging checkout only"
            className="w-full rounded-lg border border-mist-300/15 bg-ink-950/50 px-3 py-2 font-mono text-sm text-mist-50 outline-none focus:ring-2 focus:ring-signal-sky/40"
            disabled={loading}
          />
        </div>

        <button
          type="submit"
          disabled={loading || !repoKey || errorText.trim().length < 5}
          className="rounded-lg bg-signal-sky px-4 py-2.5 font-mono text-sm font-semibold tracking-wide text-ink-950 transition hover:brightness-110 disabled:cursor-wait disabled:opacity-70"
        >
          {loading ? "Starting Cursor agent…" : "Start Cursor fix"}
        </button>
        {error && !showPasswordModal ? (
          <p className="font-mono text-xs text-signal-rose">{error}</p>
        ) : null}
      </form>

      {showPasswordModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/80 px-4 backdrop-blur-sm">
          <div className="w-full max-w-md space-y-4 rounded-xl border border-mist-300/15 bg-ink-950 p-6 shadow-xl">
            <div className="space-y-1">
              <p className="label">Authorization</p>
              <h2 className="font-display text-xl font-semibold text-mist-50">
                Enter fix password
              </h2>
              <p className="text-sm text-mist-400">
                Required before starting a Cursor Cloud fix job.
              </p>
            </div>
            <input
              type="password"
              autoFocus
              value={fixPassword}
              onChange={(e) => setFixPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void confirmStartFix();
                }
              }}
              placeholder="Fix password"
              className="w-full rounded-lg border border-mist-300/15 bg-ink-950/50 px-3 py-2.5 font-mono text-sm text-mist-50 outline-none focus:ring-2 focus:ring-signal-sky/40"
              disabled={loading}
            />
            {error ? (
              <p className="font-mono text-xs text-signal-rose">{error}</p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowPasswordModal(false);
                  setFixPassword("");
                  setError(null);
                }}
                disabled={loading}
                className="rounded-lg border border-mist-300/20 px-4 py-2 font-mono text-sm text-mist-300 transition hover:bg-ink-950/60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void confirmStartFix()}
                disabled={loading || !fixPassword.trim()}
                className="rounded-lg bg-signal-sky px-4 py-2 font-mono text-sm font-semibold text-ink-950 transition hover:brightness-110 disabled:opacity-70"
              >
                {loading ? "Starting…" : "Confirm & start"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <section className="space-y-3">
        <p className="label">Recent fix jobs</p>
        <div className="overflow-hidden rounded-xl border border-mist-300/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink-950/60 font-mono text-xs uppercase tracking-wider text-mist-400">
              <tr>
                <th className="px-4 py-3">Job</th>
                <th className="px-4 py-3">Repo</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Branches</th>
                <th className="px-4 py-3">When</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-mist-400">
                    No fix jobs yet
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="border-t border-mist-300/10 hover:bg-ink-950/40"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/fixes/${job.id}`}
                        className="font-mono text-signal-sky hover:underline"
                      >
                        {shortId(job.id)}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-mono text-mist-200">
                      {job.repo_key}
                    </td>
                    <td className={`px-4 py-3 font-mono ${statusClass(job.status)}`}>
                      {job.status}
                    </td>
                    <td className="max-w-[220px] truncate px-4 py-3 font-mono text-xs text-mist-400">
                      {job.backup_branch || "—"} → {job.fix_branch || "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-mist-400">
                      {formatTime(job.created_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { investigateIssue } from "@/lib/api";

const EXAMPLES = [
  "my signyn website is not working",
  "node-server seems down",
  "website is slow / not loading",
];

export function InvestigateBox({ onDone }: { onDone?: () => void }) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const text = message.trim();
    if (text.length < 3) {
      setError("Describe the issue in a few words.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const incident = await investigateIssue({ message: text });
      onDone?.();
      router.push(`/incidents/${incident.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Investigation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="panel w-full max-w-xl space-y-3 p-4">
      <div>
        <p className="label">Report an issue</p>
        <p className="mt-1 text-sm text-mist-300">
          Describe what&apos;s wrong. Aegis will check health, CloudWatch, PM2
          (<span className="font-mono text-mist-200">signyn</span>,{" "}
          <span className="font-mono text-mist-200">node-server</span>), and
          MySQL (prod/staging).
        </p>
      </div>
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={3}
        placeholder='e.g. "my signyn website is not working / running"'
        className="w-full resize-y rounded-lg border border-mist-300/15 bg-ink-950/50 px-3 py-2 font-mono text-sm text-mist-50 outline-none ring-signal-sky/40 placeholder:text-mist-500 focus:ring-2"
        disabled={loading}
      />
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={loading}
            onClick={() => setMessage(example)}
            className="rounded border border-mist-300/15 px-2 py-1 font-mono text-[11px] text-mist-400 hover:border-mist-300/30 hover:text-mist-200 disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={run}
        disabled={loading}
        className="rounded-lg bg-signal-sky px-4 py-2.5 font-mono text-sm font-semibold tracking-wide text-ink-950 transition hover:brightness-110 disabled:cursor-wait disabled:opacity-70"
      >
        {loading ? "Investigating on AWS…" : "Investigate issue"}
      </button>
      {error ? (
        <p className="font-mono text-xs text-signal-rose">{error}</p>
      ) : null}
    </div>
  );
}

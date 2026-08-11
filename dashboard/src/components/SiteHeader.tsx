"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchHealth, getApiUrl } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

export function SiteHeader() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const data = await fetchHealth();
        if (active) setHealth(data);
      } catch {
        if (active) setHealth(null);
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const dbUp = health?.database === "up";

  return (
    <header className="border-b border-mist-300/10 bg-ink-950/70 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-6">
          <Link href="/" className="group flex items-baseline gap-3">
            <span className="font-display text-3xl font-semibold tracking-tight text-mist-50 transition group-hover:text-signal-amber">
              Aegis
            </span>
            <span className="hidden font-mono text-xs uppercase tracking-[0.2em] text-mist-400 sm:inline">
              Agent Console
            </span>
          </Link>
          <nav className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.14em]">
            <Link
              href="/"
              className="text-mist-400 transition hover:text-mist-50"
            >
              Ops
            </Link>
            <Link
              href="/fixes"
              className="text-mist-400 transition hover:text-signal-sky"
            >
              Code Fixes
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-4 text-xs">
          <div className="hidden items-center gap-2 font-mono text-mist-300 md:flex">
            <span
              className={`h-2 w-2 rounded-full ${dbUp ? "bg-signal-mint animate-pulseSoft" : "bg-signal-rose"}`}
            />
            <span>
              API {health ? health.status : "…"} · DB{" "}
              {health?.database ?? "…"} · mode{" "}
              {health?.agent_mode ?? "…"} · tools{" "}
              {health?.tool_backend ?? "…"}
              {health?.aws_configured ? " · aws✓" : ""}
            </span>
          </div>
          <span className="max-w-[180px] truncate font-mono text-mist-400" title={getApiUrl()}>
            {getApiUrl().replace("http://", "")}
          </span>
        </div>
      </div>
    </header>
  );
}
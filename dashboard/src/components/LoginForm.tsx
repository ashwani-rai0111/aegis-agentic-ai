"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { login } from "@/lib/api";
import { setSession } from "@/lib/auth";

export function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await login(username.trim(), password);
      setSession(result.token, result.username);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center animate-fade-up">
      <div className="space-y-2 text-center">
        <p className="label">Aegis access</p>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-mist-50">
          Sign in
        </h1>
      </div>

      <form
        onSubmit={onSubmit}
        className="mt-8 space-y-4 rounded-xl border border-mist-300/10 bg-ink-950/50 p-6"
      >
        <div className="space-y-2">
          <label className="label" htmlFor="username">
            Username
          </label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-lg border border-mist-300/15 bg-ink-950/50 px-3 py-2.5 font-mono text-sm text-mist-50 outline-none focus:ring-2 focus:ring-signal-sky/40"
            disabled={loading}
            required
          />
        </div>
        <div className="space-y-2">
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-mist-300/15 bg-ink-950/50 px-3 py-2.5 font-mono text-sm text-mist-50 outline-none focus:ring-2 focus:ring-signal-sky/40"
            disabled={loading}
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading || !username || !password}
          className="w-full rounded-lg bg-signal-sky px-4 py-2.5 font-mono text-sm font-semibold tracking-wide text-ink-950 transition hover:brightness-110 disabled:cursor-wait disabled:opacity-70"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
        {error ? (
          <p className="font-mono text-xs text-signal-rose">{error}</p>
        ) : null}
      </form>
    </div>
  );
}

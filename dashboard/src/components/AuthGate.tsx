"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearSession, getSessionToken, isLoggedIn } from "@/lib/auth";
import { verifySession } from "@/lib/api";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const isLogin = pathname === "/login";

  useEffect(() => {
    let active = true;

    async function check() {
      if (isLogin) {
        if (isLoggedIn()) {
          router.replace("/");
          return;
        }
        if (active) setReady(true);
        return;
      }

      const token = getSessionToken();
      if (!token) {
        router.replace("/login");
        return;
      }

      try {
        const session = await verifySession(token);
        if (!session.ok) {
          clearSession();
          router.replace("/login");
          return;
        }
        if (active) setReady(true);
      } catch {
        clearSession();
        router.replace("/login");
      }
    }

    setReady(false);
    void check();
    return () => {
      active = false;
    };
  }, [isLogin, pathname, router]);

  if (!ready) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center font-mono text-sm text-mist-400">
        Checking session…
      </div>
    );
  }

  return <>{children}</>;
}

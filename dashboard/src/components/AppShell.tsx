"use client";

import { usePathname } from "next/navigation";
import { AuthGate } from "@/components/AuthGate";
import { SiteHeader } from "@/components/SiteHeader";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  return (
    <AuthGate>
      {isLogin ? null : <SiteHeader />}
      <main
        className={
          isLogin
            ? "mx-auto max-w-7xl px-6 py-8"
            : "mx-auto max-w-7xl px-6 py-8"
        }
      >
        {children}
      </main>
    </AuthGate>
  );
}

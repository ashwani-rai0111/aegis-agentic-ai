import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Sora } from "next/font/google";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

const sans = IBM_Plex_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

const display = Sora({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Aegis — Operations Console",
  description:
    "Live incident timeline, agent reasoning, approvals, and verification for Aegis.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${sans.variable} ${mono.variable} ${display.variable} bg-ink-950 font-sans text-mist-100 antialiased`}
      >
        <div className="min-h-screen bg-ops-glow">
          <div className="min-h-screen bg-ops-grid bg-grid">
            <SiteHeader />
            <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
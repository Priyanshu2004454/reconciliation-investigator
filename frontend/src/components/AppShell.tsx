"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import { CopilotPanel } from "./CopilotPanel";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/reconciliation", label: "Reconciliation" },
  { href: "/bank-statements", label: "Data Imports" },
  { href: "/audit-log", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [copilotOpen, setCopilotOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] text-sm text-[var(--color-text-secondary)]">
        Loading session…
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex min-h-screen bg-[var(--color-bg)]">
      <aside className="flex w-60 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="border-b border-[var(--color-border)] px-5 py-5">
          <div className="text-[15px] font-semibold tracking-tight text-[var(--color-text-primary)]">
            Recon<span className="text-[var(--color-primary)]">Investigator</span>
          </div>
          <div className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">Test Mode</div>
        </div>

        <nav className="flex-1 px-3 py-4">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`mb-1 block rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                  active
                    ? "bg-[var(--color-primary-bg)] text-[var(--color-primary)]"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}

          <div className="my-3 border-t border-[var(--color-border)]" />

          <button
            onClick={() => setCopilotOpen(true)}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[13px] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-ai-accent-bg)] hover:text-[var(--color-ai-accent)]"
          >
            <span className="text-[var(--color-ai-accent)]">✦</span>
            AI Copilot
            <span className="ml-auto rounded-full bg-[var(--color-ai-accent-bg)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--color-ai-accent)]">
              BETA
            </span>
          </button>
        </nav>

        <div className="border-t border-[var(--color-border)] px-5 py-4">
          <div className="truncate text-[12px] text-[var(--color-text-secondary)]">{user.email}</div>
          <button
            onClick={logout}
            className="mt-1.5 text-[11px] font-medium text-[var(--color-text-muted)] hover:text-[var(--color-critical)]"
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
      </main>

      <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/reconciliation", label: "Reconciliation" },
  { href: "/bank-statements", label: "Bank Statements" },
  { href: "/audit-log", label: "Audit Log" },
  { href: "/settings", label: "Settings" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] text-[var(--color-text-secondary)] font-mono text-sm">
        Loading session…
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex min-h-screen bg-[var(--color-bg)]">
      <aside className="flex w-56 shrink-0 flex-col border-r border-[var(--color-border)]">
        <div className="border-b border-[var(--color-border)] px-5 py-5">
          <div className="font-mono text-[13px] font-semibold tracking-tight text-[var(--color-text-primary)]">
            RECON<span className="text-[var(--color-explained)]">/</span>INVESTIGATOR
          </div>
          <div className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Test Mode Ledger
          </div>
        </div>

        <nav className="flex-1 px-3 py-4">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`mb-1 block rounded-sm px-3 py-2 text-[13px] transition-colors ${
                  active
                    ? "bg-[var(--color-surface)] text-[var(--color-text-primary)] border-l-2 border-[var(--color-explained)]"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)] border-l-2 border-transparent"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-[var(--color-border)] px-5 py-4">
          <div className="truncate text-[12px] text-[var(--color-text-secondary)]">{user.email}</div>
          <button
            onClick={logout}
            className="mt-2 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-critical)]"
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
      </main>
    </div>
  );
}

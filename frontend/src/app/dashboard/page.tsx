"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { PageHeader, SummaryCard, Card, LoadingState, ErrorState, EmptyState } from "@/components/ui";
import { StatusStamp } from "@/components/StatusStamp";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { DashboardSummary, RecentActivityItem, MismatchCategoryBreakdown } from "@/lib/types";

function formatRupees(n: number): string {
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export default function DashboardPage() {
  const { merchantAccount, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [activity, setActivity] = useState<RecentActivityItem[]>([]);
  const [breakdown, setBreakdown] = useState<MismatchCategoryBreakdown[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading || !merchantAccount) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [s, a, b] = await Promise.all([
          api.getDashboardSummary(),
          api.getRecentActivity(8),
          api.getMismatchBreakdown(),
        ]);
        if (!cancelled) {
          setSummary(s);
          setActivity(a);
          setBreakdown(b);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load dashboard data.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, merchantAccount]);

  return (
    <AppShell>
      <PageHeader
        title="Dashboard"
        description="Live reconciliation status across your Razorpay test-mode account."
      />

      {!authLoading && !merchantAccount && (
        <EmptyState
          title="No merchant account connected yet"
          description="Head to Settings to connect your Razorpay Test Mode account before reconciliation data can appear here."
        />
      )}

      {merchantAccount && loading && <LoadingState label="Loading dashboard…" />}
      {merchantAccount && error && <ErrorState message={error} />}

      {merchantAccount && summary && !loading && !error && (
        <div className="space-y-8">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <SummaryCard label="Total Transactions" value={summary.total_transactions.toLocaleString("en-IN")} />
            <SummaryCard label="Processed Value" value={formatRupees(summary.processed_value)} />
            <SummaryCard
              label="Matched"
              value={summary.matched_count.toLocaleString("en-IN")}
              accent="var(--color-matched)"
            />
            <SummaryCard
              label="Explained"
              value={summary.explained_count.toLocaleString("en-IN")}
              accent="var(--color-explained)"
            />
            <SummaryCard
              label="Needs Review"
              value={summary.needs_review_count.toLocaleString("en-IN")}
              accent="var(--color-review)"
            />
            <SummaryCard
              label="Reconciliation Rate"
              value={`${summary.reconciliation_rate}%`}
              accent="var(--color-matched)"
            />
            <SummaryCard
              label="Requires Investigation"
              value={formatRupees(summary.amount_requiring_investigation)}
              accent="var(--color-critical)"
            />
            <SummaryCard
              label="Last Run"
              value={summary.last_run_status ?? "—"}
              sublabel={summary.last_run_at ? new Date(summary.last_run_at).toLocaleString("en-IN") : undefined}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <div className="border-b border-[var(--color-border)] px-5 py-3 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Recent Activity
              </div>
              {activity.length === 0 ? (
                <div className="px-5 py-8 text-center text-sm text-[var(--color-text-secondary)]">
                  No reconciliation cases yet.
                </div>
              ) : (
                <div className="divide-y divide-[var(--color-border)]">
                  {activity.map((item) => (
                    <Link
                      key={item.case_id}
                      href={`/reconciliation/${item.case_id}`}
                      className="flex items-center justify-between px-5 py-3 hover:bg-[var(--color-surface-hover)]"
                    >
                      <div>
                        <div className="font-mono text-xs text-[var(--color-text-secondary)]">
                          {item.razorpay_settlement_id ?? item.case_id.slice(0, 8)}
                        </div>
                        <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                          {new Date(item.updated_at).toLocaleString("en-IN")}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {item.amount !== null && (
                          <span className="font-mono text-xs tabular text-[var(--color-text-secondary)]">
                            {formatRupees(item.amount)}
                          </span>
                        )}
                        <StatusStamp status={item.status} />
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </Card>

            <Card className="lg:col-span-2">
              <div className="border-b border-[var(--color-border)] px-5 py-3 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Top Mismatch Categories
              </div>
              {breakdown.length === 0 ? (
                <div className="px-5 py-8 text-center text-sm text-[var(--color-text-secondary)]">
                  No investigated mismatches yet.
                </div>
              ) : (
                <div className="divide-y divide-[var(--color-border)]">
                  {breakdown.map((b) => (
                    <div key={b.category} className="flex items-center justify-between px-5 py-3">
                      <span className="font-mono text-xs text-[var(--color-text-secondary)]">
                        {b.category.replace(/_/g, " ")}
                      </span>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-[var(--color-text-muted)]">{b.count}×</span>
                        <span className="font-mono text-xs tabular text-[var(--color-text-primary)]">
                          {formatRupees(b.total_amount)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </div>
      )}
    </AppShell>
  );
}

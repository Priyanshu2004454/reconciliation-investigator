"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { PageHeader, SummaryCard, Card, LoadingState, ErrorState, Button } from "@/components/ui";
import { StatusStamp } from "@/components/StatusStamp";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { DashboardSummary, RecentActivityItem, MismatchCategoryBreakdown } from "@/lib/types";

function formatRupees(n: number): string {
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function ReconciliationDonut({ matched, explained, needsReview }: { matched: number; explained: number; needsReview: number }) {
  const total = matched + explained + needsReview || 1;
  const matchedPct = (matched / total) * 100;
  const explainedPct = (explained / total) * 100;
  const reviewPct = (needsReview / total) * 100;

  const gradient = `conic-gradient(
    var(--color-matched) 0% ${matchedPct}%,
    var(--color-explained) ${matchedPct}% ${matchedPct + explainedPct}%,
    var(--color-review) ${matchedPct + explainedPct}% ${matchedPct + explainedPct + reviewPct}%
  )`;

  return (
    <div className="flex items-center gap-6">
      <div className="relative h-28 w-28 shrink-0 rounded-full" style={{ background: gradient }}>
        <div className="absolute inset-2.5 flex flex-col items-center justify-center rounded-full bg-white">
          <div className="text-lg font-semibold tabular text-[var(--color-text-primary)]">{total}</div>
          <div className="text-[10px] text-[var(--color-text-muted)]">total</div>
        </div>
      </div>
      <div className="space-y-2 text-[13px]">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: "var(--color-matched)" }} />
          <span className="text-[var(--color-text-secondary)]">Matched</span>
          <span className="ml-auto font-medium tabular text-[var(--color-text-primary)]">{matched}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: "var(--color-explained)" }} />
          <span className="text-[var(--color-text-secondary)]">Explained</span>
          <span className="ml-auto font-medium tabular text-[var(--color-text-primary)]">{explained}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: "var(--color-review)" }} />
          <span className="text-[var(--color-text-secondary)]">Needs Review</span>
          <span className="ml-auto font-medium tabular text-[var(--color-text-primary)]">{needsReview}</span>
        </div>
      </div>
    </div>
  );
}

function AIInsights({ summary, breakdown }: { summary: DashboardSummary; breakdown: MismatchCategoryBreakdown[] }) {
  const topIssue = breakdown[0];
  const insights: string[] = [];

  if (summary.needs_review_count > 0) {
    insights.push(`${summary.needs_review_count} case${summary.needs_review_count === 1 ? "" : "s"} need attention`);
  }
  if (topIssue) {
    insights.push(`Top issue: ${topIssue.category.replace(/_/g, " ").toLowerCase()}`);
  }
  if (summary.amount_requiring_investigation > 0) {
    insights.push(`${formatRupees(summary.amount_requiring_investigation)} tied up in unresolved cases`);
  }
  if (summary.reconciliation_rate >= 95) {
    insights.push(`Reconciliation rate is healthy at ${summary.reconciliation_rate}%`);
  }

  if (insights.length === 0) {
    insights.push("No issues detected -- everything is reconciled.");
  }

  return (
    <div className="space-y-2.5">
      {insights.slice(0, 4).map((text, i) => (
        <div key={i} className="flex items-start gap-2 text-[13px] text-[var(--color-text-primary)]">
          <span className="mt-0.5 text-[var(--color-ai-accent)]">✦</span>
          {text}
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { user, merchantAccount, loading: authLoading } = useAuth();
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
        title={`${greeting()}${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}`}
        description="Here's the current state of your reconciliation."
      />

      {!authLoading && !merchantAccount && (
        <Card className="p-6">
          <div className="max-w-lg space-y-3">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
              No transactions recorded yet
            </h3>
            <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
              Head to Reconciliation to load the demo dataset and run the engine, or connect a real
              Razorpay Test Mode account in Settings.
            </p>
            <div className="pt-1">
              <Link href="/reconciliation">
                <Button>Go to Reconciliation →</Button>
              </Link>
            </div>
          </div>
        </Card>
      )}

      {merchantAccount && loading && <LoadingState label="Loading dashboard…" />}
      {merchantAccount && error && <ErrorState message={error} />}

      {merchantAccount && summary && !loading && !error && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <SummaryCard label="Total Transactions" value={summary.total_transactions.toLocaleString("en-IN")} />
            <SummaryCard label="Reconciled" value={`${summary.reconciliation_rate}%`} accent="var(--color-matched)" />
            <SummaryCard
              label="Needs Review"
              value={summary.needs_review_count.toLocaleString("en-IN")}
              accent="var(--color-review)"
            />
            <SummaryCard
              label="Amount Difference"
              value={formatRupees(summary.amount_requiring_investigation)}
              accent="var(--color-critical)"
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
            <Card className="p-5 lg:col-span-2">
              <div className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">Reconciliation Summary</div>
              <ReconciliationDonut
                matched={summary.matched_count}
                explained={summary.explained_count}
                needsReview={summary.needs_review_count}
              />
            </Card>

            <Card className="p-5 lg:col-span-3">
              <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
                <span className="text-[var(--color-ai-accent)]">✦</span> AI Insights
              </div>
              <AIInsights summary={summary} breakdown={breakdown} />
            </Card>
          </div>

          <Card>
            <div className="border-b border-[var(--color-border)] px-5 py-3.5 text-sm font-semibold text-[var(--color-text-primary)]">
              Recent Activity
            </div>
            {activity.length === 0 ? (
              <div className="px-5 py-10 text-center text-sm text-[var(--color-text-secondary)]">
                No reconciliation cases yet.
              </div>
            ) : (
              <div className="divide-y divide-[var(--color-border)]">
                {activity.map((item) => (
                  <Link
                    key={item.case_id}
                    href={`/reconciliation/${item.case_id}`}
                    className="flex items-center justify-between px-5 py-3 transition-colors hover:bg-[var(--color-surface-hover)]"
                  >
                    <div>
                      <div className="text-[13px] font-medium text-[var(--color-text-primary)]">
                        {item.razorpay_settlement_id ?? item.case_id.slice(0, 8)}
                      </div>
                      <div className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                        {new Date(item.updated_at).toLocaleString("en-IN")}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {item.amount !== null && (
                        <span className="text-[13px] tabular text-[var(--color-text-secondary)]">
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
        </div>
      )}
    </AppShell>
  );
}

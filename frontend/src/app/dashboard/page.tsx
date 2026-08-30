"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Card, LoadingState, ErrorState, EmptyState, Button } from "@/components/ui";
import { StatusStamp } from "@/components/StatusStamp";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type {
  DashboardSummary,
  RecentActivityItem,
  MismatchCategoryBreakdown,
  ReconciliationRun,
  ExceptionCase,
} from "@/lib/types";

function formatRupees(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function pct(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

// ── KPI card ────────────────────────────────────────────────────────────
function KpiCard({
  icon,
  label,
  value,
  sublabel,
  accent,
}: {
  icon: string;
  label: string;
  value: string;
  sublabel: string;
  accent: string;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-lg text-sm"
          style={{ backgroundColor: `${accent}1A`, color: accent }}
        >
          {icon}
        </span>
        <span className="text-[13px] font-medium text-[var(--color-text-secondary)]">{label}</span>
      </div>
      <div className="mt-3 text-2xl font-semibold tabular text-[var(--color-text-primary)]">{value}</div>
      <div className="mt-1 text-xs text-[var(--color-text-muted)]">{sublabel}</div>
    </Card>
  );
}

// ── Reconciliation health donut ─────────────────────────────────────────
function ReconciliationDonut({ matched, explained, needsReview }: { matched: number; explained: number; needsReview: number }) {
  const total = matched + explained + needsReview || 1;
  const matchedPct = (matched / total) * 100;
  const explainedPct = (explained / total) * 100;
  const reviewPct = (needsReview / total) * 100;
  const rate = Math.round(((matched + explained) / total) * 100);

  const gradient = `conic-gradient(
    var(--color-matched) 0% ${matchedPct}%,
    var(--color-explained) ${matchedPct}% ${matchedPct + explainedPct}%,
    var(--color-review) ${matchedPct + explainedPct}% ${matchedPct + explainedPct + reviewPct}%
  )`;

  return (
    <div className="flex items-center gap-8">
      <div className="relative h-32 w-32 shrink-0 rounded-full" style={{ background: gradient }}>
        <div className="absolute inset-3 flex flex-col items-center justify-center rounded-full bg-white">
          <div className="text-2xl font-semibold tabular text-[var(--color-text-primary)]">{rate}%</div>
          <div className="text-[10px] text-[var(--color-text-muted)]">Reconciled</div>
        </div>
      </div>
      <div className="space-y-2.5 text-[13px]">
        <div className="flex items-center gap-2.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-matched)" }} />
          <span className="w-20 text-[var(--color-text-secondary)]">Matched</span>
          <span className="w-8 text-right font-medium tabular text-[var(--color-text-primary)]">{matched}</span>
          <span className="text-xs text-[var(--color-text-muted)]">{pct(matched, total)}</span>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-explained)" }} />
          <span className="w-20 text-[var(--color-text-secondary)]">Explained</span>
          <span className="w-8 text-right font-medium tabular text-[var(--color-text-primary)]">{explained}</span>
          <span className="text-xs text-[var(--color-text-muted)]">{pct(explained, total)}</span>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-review)" }} />
          <span className="w-20 text-[var(--color-text-secondary)]">Needs Review</span>
          <span className="w-8 text-right font-medium tabular text-[var(--color-text-primary)]">{needsReview}</span>
          <span className="text-xs text-[var(--color-text-muted)]">{pct(needsReview, total)}</span>
        </div>
      </div>
    </div>
  );
}

const SEVERITY_STYLE: Record<string, { bg: string; color: string }> = {
  HIGH: { bg: "var(--color-critical-bg)", color: "var(--color-critical)" },
  MEDIUM: { bg: "var(--color-review-bg)", color: "var(--color-review)" },
  LOW: { bg: "var(--color-explained-bg)", color: "var(--color-explained)" },
};

function severityFor(amount: number | null): "HIGH" | "MEDIUM" | "LOW" {
  if (amount === null) return "LOW";
  if (amount >= 10000) return "HIGH";
  if (amount >= 2000) return "MEDIUM";
  return "LOW";
}

export default function DashboardPage() {
  const { merchantAccount, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [activity, setActivity] = useState<RecentActivityItem[]>([]);
  const [breakdown, setBreakdown] = useState<MismatchCategoryBreakdown[]>([]);
  const [runs, setRuns] = useState<ReconciliationRun[]>([]);
  const [exceptions, setExceptions] = useState<ExceptionCase[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, a, b, r, e] = await Promise.all([
        api.getDashboardSummary(),
        api.getRecentActivity(8),
        api.getMismatchBreakdown(),
        api.listReconciliationRuns(7).catch(() => []),
        api.listExceptions().catch(() => []),
      ]);
      setSummary(s);
      setActivity(a);
      setBreakdown(b);
      setRuns(r.slice().reverse());
      setExceptions(e);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load dashboard data.");
    }
  }, []);

  useEffect(() => {
    if (authLoading || !merchantAccount) {
      setLoading(false);
      return;
    }
    setLoading(true);
    load().finally(() => setLoading(false));
  }, [authLoading, merchantAccount, load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const totalBreakdownCount = breakdown.reduce((sum, b) => sum + b.count, 0);
  const maxBreakdownAmount = Math.max(...breakdown.map((b) => b.total_amount), 1);
  const totalCases = summary ? summary.matched_count + summary.explained_count + summary.needs_review_count : 0;
  const maxRunAmount = Math.max(...runs.map((r) => r.match_rate), 1);

  return (
    <AppShell>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-text-primary)]">Overview</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            Real-time reconciliation insights
            {merchantAccount?.business_name ? ` for ${merchantAccount.business_name}` : ""}
          </p>
        </div>
        {merchantAccount && (
          <Button variant="secondary" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "↻ Refresh"}
          </Button>
        )}
      </div>

      {!authLoading && !merchantAccount && (
        <Card className="p-6">
          <div className="max-w-lg space-y-3">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">No transactions recorded yet</h3>
            <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
              Head to Reconciliation to load the demo dataset and run the engine, or connect a real Razorpay
              Test Mode account in Settings.
            </p>
            <Link href="/reconciliation">
              <Button>Go to Reconciliation →</Button>
            </Link>
          </div>
        </Card>
      )}

      {merchantAccount && loading && <LoadingState label="Loading dashboard…" />}
      {merchantAccount && error && <ErrorState message={error} />}

      {merchantAccount && summary && !loading && !error && (
        <div className="space-y-6">
          {/* KPI cards */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KpiCard
              icon="▤"
              label="Total Processed"
              value={formatRupees(summary.processed_value)}
              sublabel={`${summary.total_transactions.toLocaleString("en-IN")} transactions`}
              accent="var(--color-primary)"
            />
            <KpiCard
              icon="✓"
              label="Matched"
              value={String(summary.matched_count)}
              sublabel={pct(summary.matched_count, totalCases) + " of total"}
              accent="var(--color-matched)"
            />
            <KpiCard
              icon="i"
              label="Explained"
              value={String(summary.explained_count)}
              sublabel={pct(summary.explained_count, totalCases) + " of total"}
              accent="var(--color-explained)"
            />
            <KpiCard
              icon="!"
              label="Needs Review"
              value={String(summary.needs_review_count)}
              sublabel={`${formatRupees(summary.amount_requiring_investigation)} at risk`}
              accent="var(--color-review)"
            />
          </div>

          {/* Health + Needs Attention */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card className="p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Reconciliation Health</h2>
                <Link href="/reconciliation" className="text-xs font-medium text-[var(--color-primary)] hover:underline">
                  View all cases →
                </Link>
              </div>
              <ReconciliationDonut
                matched={summary.matched_count}
                explained={summary.explained_count}
                needsReview={summary.needs_review_count}
              />
            </Card>

            <Card className="p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Needs Attention</h2>
                <Link href="/reconciliation" className="text-xs font-medium text-[var(--color-primary)] hover:underline">
                  View all {summary.needs_review_count} cases →
                </Link>
              </div>
              {exceptions.length === 0 ? (
                <div className="py-8 text-center text-sm text-[var(--color-text-secondary)]">
                  No exceptions requiring attention.
                </div>
              ) : (
                <div className="space-y-3">
                  {exceptions
                    .slice()
                    .sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0))
                    .slice(0, 3)
                    .map((exc) => {
                      const sev = severityFor(exc.amount);
                      const style = SEVERITY_STYLE[sev];
                      return (
                        <Link
                          key={exc.case_id}
                          href={`/reconciliation/${exc.case_id}`}
                          className="flex items-center gap-3 rounded-lg px-2 py-1.5 transition-colors hover:bg-[var(--color-surface-hover)]"
                        >
                          <span
                            className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
                            style={{ backgroundColor: style.bg, color: style.color }}
                          >
                            {sev}
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-[13px] font-medium text-[var(--color-text-primary)]">
                              {exc.mismatch_type ? exc.mismatch_type.replace(/_/g, " ") : "Needs Review"}
                            </div>
                            <div className="truncate text-[11px] text-[var(--color-text-muted)]">
                              {exc.razorpay_settlement_id ?? exc.case_id.slice(0, 8)}
                            </div>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="text-[13px] font-medium tabular text-[var(--color-text-primary)]">
                              {formatRupees(exc.amount)}
                            </div>
                            <div className="text-[11px] text-[var(--color-text-muted)]">{formatDate(exc.created_at)}</div>
                          </div>
                        </Link>
                      );
                    })}
                </div>
              )}
            </Card>
          </div>

          {/* Recent runs + AI Suggested Actions */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card className="p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Recent Reconciliation Runs</h2>
              </div>
              {runs.length === 0 ? (
                <EmptyState title="No runs yet" description="Run reconciliation to see match-rate history here." />
              ) : (
                <div className="flex h-32 items-end gap-3">
                  {runs.map((r) => (
                    <div key={r.id} className="flex flex-1 flex-col items-center gap-1.5">
                      <span className="text-[11px] font-medium tabular text-[var(--color-text-primary)]">
                        {r.match_rate}%
                      </span>
                      <div
                        className="w-full rounded-t-md"
                        style={{
                          height: `${Math.max((r.match_rate / maxRunAmount) * 72, 4)}px`,
                          backgroundColor: r.match_rate >= 90 ? "var(--color-matched)" : "var(--color-review)",
                        }}
                      />
                      <span className="text-[10px] text-[var(--color-text-muted)]">{formatDate(r.started_at)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card className="p-6">
              <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
                <span className="text-[var(--color-ai-accent)]">✦</span> AI Suggested Actions
              </div>
              <div className="space-y-1">
                {summary.needs_review_count > 0 && (
                  <Link
                    href="/reconciliation"
                    className="flex items-center justify-between rounded-lg px-2 py-2 transition-colors hover:bg-[var(--color-ai-accent-bg)]"
                  >
                    <div>
                      <div className="text-[13px] font-medium text-[var(--color-text-primary)]">
                        Review {summary.needs_review_count} unresolved case{summary.needs_review_count === 1 ? "" : "s"}
                      </div>
                      <div className="text-[11.5px] text-[var(--color-text-muted)]">
                        Total amount: {formatRupees(summary.amount_requiring_investigation)}
                      </div>
                    </div>
                    <span className="text-[var(--color-text-muted)]">›</span>
                  </Link>
                )}
                {breakdown[0] && (
                  <Link
                    href="/reconciliation"
                    className="flex items-center justify-between rounded-lg px-2 py-2 transition-colors hover:bg-[var(--color-ai-accent-bg)]"
                  >
                    <div>
                      <div className="text-[13px] font-medium text-[var(--color-text-primary)]">
                        Investigate top issue: {breakdown[0].category.replace(/_/g, " ").toLowerCase()}
                      </div>
                      <div className="text-[11.5px] text-[var(--color-text-muted)]">
                        {breakdown[0].count} cases · {formatRupees(breakdown[0].total_amount)}
                      </div>
                    </div>
                    <span className="text-[var(--color-text-muted)]">›</span>
                  </Link>
                )}
                {summary.reconciliation_rate >= 95 && (
                  <div className="flex items-center justify-between rounded-lg px-2 py-2">
                    <div>
                      <div className="text-[13px] font-medium text-[var(--color-text-primary)]">
                        Reconciliation rate healthy at {summary.reconciliation_rate}%
                      </div>
                      <div className="text-[11.5px] text-[var(--color-text-muted)]">No action needed</div>
                    </div>
                  </div>
                )}
                {summary.needs_review_count === 0 && breakdown.length === 0 && (
                  <div className="py-6 text-center text-sm text-[var(--color-text-secondary)]">
                    No suggested actions -- everything is reconciled.
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Top exception reasons */}
          {breakdown.length > 0 && (
            <Card className="p-6">
              <h2 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">Top Exception Reasons</h2>
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                    <th className="pb-2.5">Reason</th>
                    <th className="pb-2.5 text-right">Cases</th>
                    <th className="pb-2.5 text-right">Amount Involved</th>
                    <th className="pb-2.5 text-right">% of Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {breakdown.map((b) => (
                    <tr key={b.category}>
                      <td className="py-2.5 text-[13px] font-medium text-[var(--color-text-primary)]">
                        {b.category.replace(/_/g, " ")}
                      </td>
                      <td className="py-2.5 text-right text-[13px] tabular text-[var(--color-text-secondary)]">
                        {b.count}
                      </td>
                      <td className="py-2.5 text-right text-[13px] tabular text-[var(--color-text-secondary)]">
                        {formatRupees(b.total_amount)}
                      </td>
                      <td className="py-2.5">
                        <div className="flex items-center justify-end gap-2">
                          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--color-surface-hover)]">
                            <div
                              className="h-full rounded-full bg-[var(--color-primary)]"
                              style={{ width: `${(b.total_amount / maxBreakdownAmount) * 100}%` }}
                            />
                          </div>
                          <span className="w-9 text-right text-xs tabular text-[var(--color-text-muted)]">
                            {pct(b.count, totalBreakdownCount)}
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          {/* Recent activity */}
          <Card>
            <div className="border-b border-[var(--color-border)] px-6 py-3.5 text-sm font-semibold text-[var(--color-text-primary)]">
              Recent Activity
            </div>
            {activity.length === 0 ? (
              <div className="px-6 py-10 text-center text-sm text-[var(--color-text-secondary)]">
                No reconciliation cases yet.
              </div>
            ) : (
              <div className="divide-y divide-[var(--color-border)]">
                {activity.map((item) => (
                  <Link
                    key={item.case_id}
                    href={`/reconciliation/${item.case_id}`}
                    className="flex items-center justify-between px-6 py-3 transition-colors hover:bg-[var(--color-surface-hover)]"
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

"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { PageHeader, Card, LoadingState, ErrorState, EmptyState, Button } from "@/components/ui";
import { StatusStamp } from "@/components/StatusStamp";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { ReconciliationCaseListItem, ReconciliationStatus, SyncResult } from "@/lib/types";

const STATUS_FILTERS: (ReconciliationStatus | "ALL")[] = [
  "ALL",
  "MATCHED",
  "EXPLAINED",
  "NEEDS_REVIEW",
  "RESOLVED",
  "FALSE_POSITIVE",
];

function formatRupees(n: number | null): string {
  if (n === null) return "—";
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export default function ReconciliationPage() {
  const { merchantAccount } = useAuth();
  const [cases, setCases] = useState<ReconciliationCaseListItem[]>([]);
  const [filter, setFilter] = useState<ReconciliationStatus | "ALL">("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<"sync" | "run" | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [syncResults, setSyncResults] = useState<SyncResult[] | null>(null);

  const loadCases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listCases(filter === "ALL" ? undefined : filter);
      setCases(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load cases.");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    if (merchantAccount) {
      loadCases();
    } else {
      setLoading(false);
    }
  }, [merchantAccount, loadCases]);

  const handleSync = async () => {
    setActionBusy("sync");
    setActionMessage(null);
    setSyncResults(null);
    try {
      const results = await api.syncRazorpayData();
      setSyncResults(results);
      const totalCreated = results.reduce((sum, r) => sum + r.created, 0);
      const totalUpdated = results.reduce((sum, r) => sum + r.updated, 0);
      setActionMessage(`Synced: ${totalCreated} created, ${totalUpdated} updated across ${results.length} sources.`);
    } catch (err) {
      setActionMessage(err instanceof ApiError ? err.message : "Sync failed.");
    } finally {
      setActionBusy(null);
    }
  };

  const handleRun = async () => {
    setActionBusy("run");
    setActionMessage(null);
    try {
      const result = await api.runReconciliation();
      setActionMessage(
        `Run complete: ${result.matched} matched, ${result.explained} explained, ${result.needs_review} need review.`
      );
      await loadCases();
    } catch (err) {
      setActionMessage(err instanceof ApiError ? err.message : "Reconciliation run failed.");
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <AppShell>
      <PageHeader
        title="Reconciliation"
        description="Payments, settlements, and bank credits — matched, explained, or flagged for review."
        action={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={handleSync} disabled={actionBusy !== null}>
              {actionBusy === "sync" ? "Syncing…" : "Sync Razorpay Data"}
            </Button>
            <Button onClick={handleRun} disabled={actionBusy !== null}>
              {actionBusy === "run" ? "Running…" : "Run Reconciliation"}
            </Button>
          </div>
        }
      />

      {!merchantAccount && (
        <EmptyState
          title="No merchant account connected yet"
          description="Connect your Razorpay Test Mode account in Settings first."
        />
      )}

      {merchantAccount && (
        <>
          {actionMessage && (
            <div className="mb-4 rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-sm text-[var(--color-text-primary)]">
              {actionMessage}
            </div>
          )}

          {syncResults && (
            <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
              {syncResults.map((r) => (
                <div
                  key={r.source}
                  className="rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
                >
                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                    {r.source.replace("RAZORPAY_", "")}
                  </div>
                  <div className="mt-1 font-mono text-sm tabular text-[var(--color-text-primary)]">
                    {r.fetched} fetched
                  </div>
                  {r.errors.length > 0 && (
                    <div className="mt-1 text-[10px] text-[var(--color-critical)]">{r.errors.length} error(s)</div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="mb-4 flex gap-1.5">
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`rounded-sm border px-3 py-1.5 text-[11px] font-mono uppercase tracking-wider transition-colors ${
                  filter === s
                    ? "border-[var(--color-explained)] text-[var(--color-explained)]"
                    : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-border-strong)]"
                }`}
              >
                {s === "ALL" ? "All" : s.replace("_", " ")}
              </button>
            ))}
          </div>

          {loading && <LoadingState label="Loading cases…" />}
          {error && <ErrorState message={error} />}

          {!loading && !error && cases.length === 0 && (
            <EmptyState
              title="No cases found"
              description="Sync Razorpay data and run reconciliation to generate cases, or adjust your filter."
            />
          )}

          {!loading && !error && cases.length > 0 && (
            <Card>
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                    <th className="px-5 py-3 font-medium">Settlement</th>
                    <th className="px-5 py-3 font-medium">Rule</th>
                    <th className="px-5 py-3 font-medium text-right">Expected</th>
                    <th className="px-5 py-3 font-medium text-right">Actual</th>
                    <th className="px-5 py-3 font-medium text-right">Difference</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {cases.map((c) => (
                    <tr key={c.id} className="hover:bg-[var(--color-surface-hover)]">
                      <td className="px-5 py-3">
                        <Link href={`/reconciliation/${c.id}`} className="font-mono text-xs text-[var(--color-explained)]">
                          {c.razorpay_settlement_id ?? c.id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="px-5 py-3 font-mono text-[11px] text-[var(--color-text-muted)]">
                        {c.match_rule ?? "—"}
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-xs tabular text-[var(--color-text-secondary)]">
                        {formatRupees(c.expected_amount)}
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-xs tabular text-[var(--color-text-secondary)]">
                        {formatRupees(c.actual_amount)}
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-xs tabular text-[var(--color-text-primary)]">
                        {formatRupees(c.difference)}
                      </td>
                      <td className="px-5 py-3">
                        <StatusStamp status={c.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </AppShell>
  );
}

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
  const { merchantAccount, refreshMerchantAccount } = useAuth();
  const [cases, setCases] = useState<ReconciliationCaseListItem[]>([]);
  const [filter, setFilter] = useState<ReconciliationStatus | "ALL">("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<"sync" | "run" | "seed" | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [syncResults, setSyncResults] = useState<SyncResult[] | null>(null);

  const hasRealRazorpay = Boolean(
    merchantAccount?.razorpay_key_id && !merchantAccount.razorpay_key_id.startsWith("rzp_test_demo")
  );

  const loadCases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listCases(filter === "ALL" ? undefined : filter);
      setCases(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setCases([]);
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to load cases.");
      }
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadCases();
  }, [merchantAccount, loadCases]);

  const handleSeedDemo = async () => {
    setActionBusy("seed");
    setActionMessage(null);
    setSyncResults(null);
    try {
      const result = await api.seedDemoData();
      await refreshMerchantAccount();
      setActionMessage(
        `Demo dataset loaded: ${result.records_created} created (${result.records_existing} updated) across ${result.settlements_count} settlements, ${result.payments_count} payments, ${result.refunds_count} refunds, and ${result.bank_transactions_count} bank rows. Click "Run Reconciliation" to reconcile.`
      );
      await loadCases();
    } catch (err) {
      setActionMessage(err instanceof ApiError ? err.message : "Failed to load demo data.");
    } finally {
      setActionBusy(null);
    }
  };

  const handleSync = async () => {
    if (!hasRealRazorpay) return;
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
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              onClick={handleSeedDemo}
              disabled={actionBusy !== null}
              title="Load 100 reproducible synthetic records with known ground truth for evaluation"
            >
              {actionBusy === "seed" ? "Loading Demo…" : "Load Demo Data"}
            </Button>
            <Button
              variant="secondary"
              onClick={handleSync}
              disabled={actionBusy !== null || !hasRealRazorpay}
              title={
                hasRealRazorpay
                  ? "Sync live data from Razorpay Test Mode"
                  : "Connect a real Razorpay Test Mode key in Settings to sync live data"
              }
            >
              {actionBusy === "sync" ? "Syncing…" : "Sync Razorpay Data"}
            </Button>
            <Button
              onClick={handleRun}
              disabled={actionBusy !== null || (!merchantAccount && cases.length === 0)}
              title="Execute deterministic reconciliation engine across all stored records"
            >
              {actionBusy === "run" ? "Running…" : "Run Reconciliation"}
            </Button>
          </div>
        }
      />

      {actionMessage && (
        <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-primary-bg)] px-4 py-2.5 text-sm text-[var(--color-text-primary)]">
          {actionMessage}
        </div>
      )}

      {syncResults && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          {syncResults.map((r) => (
            <div
              key={r.source}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2.5"
            >
              <div className="text-[11px] font-medium text-[var(--color-text-muted)]">
                {r.source.replace("RAZORPAY_", "")}
              </div>
              <div className="mt-1 text-sm tabular font-medium text-[var(--color-text-primary)]">
                {r.fetched} fetched
              </div>
              {r.errors.length > 0 && (
                <div className="mt-1 text-[11px] text-[var(--color-critical)]">{r.errors.length} error(s)</div>
              )}
            </div>
          ))}
        </div>
      )}

      {!merchantAccount && cases.length === 0 && !loading && (
        <Card className="mb-6 p-6">
          <div className="max-w-xl space-y-3">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
              No transactions recorded yet
            </h3>
            <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
              Evaluate the system immediately with the 100-record synthetic dataset (UTR matches, fee/tax
              deductions, refunds, timing differences, missing bank credits, duplicates, and amount
              mismatches), or connect a real Razorpay Test Mode account in Settings.
            </p>
            <div className="flex items-center gap-3 pt-1">
              <Button onClick={handleSeedDemo} disabled={actionBusy !== null}>
                {actionBusy === "seed" ? "Loading Demo Dataset…" : "Load 100 Demo Records"}
              </Button>
              <Link href="/settings" className="text-sm font-medium text-[var(--color-primary)] hover:underline">
                Connect Razorpay Account →
              </Link>
            </div>
          </div>
        </Card>
      )}

      {(merchantAccount || cases.length > 0) && (
        <>
          <div className="mb-4 flex flex-wrap gap-1.5">
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors ${
                  filter === s
                    ? "bg-[var(--color-primary)] text-white"
                    : "bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[var(--color-border-strong)]"
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
              description="Load demo data or sync Razorpay data, then click Run Reconciliation to generate cases."
            />
          )}

          {!loading && !error && cases.length > 0 && (
            <Card className="overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg)] text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                    <th className="px-5 py-3">Settlement</th>
                    <th className="px-5 py-3">Rule</th>
                    <th className="px-5 py-3 text-right">Expected</th>
                    <th className="px-5 py-3 text-right">Actual</th>
                    <th className="px-5 py-3 text-right">Difference</th>
                    <th className="px-5 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {cases.map((c) => (
                    <tr key={c.id} className="transition-colors hover:bg-[var(--color-surface-hover)]">
                      <td className="px-5 py-3">
                        <Link href={`/reconciliation/${c.id}`} className="text-[13px] font-medium text-[var(--color-primary)] hover:underline">
                          {c.razorpay_settlement_id ?? c.id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="px-5 py-3 text-[12px] text-[var(--color-text-muted)]">
                        {c.match_rule ?? "—"}
                      </td>
                      <td className="px-5 py-3 text-right text-[13px] tabular text-[var(--color-text-secondary)]">
                        {formatRupees(c.expected_amount)}
                      </td>
                      <td className="px-5 py-3 text-right text-[13px] tabular text-[var(--color-text-secondary)]">
                        {formatRupees(c.actual_amount)}
                      </td>
                      <td className="px-5 py-3 text-right text-[13px] tabular font-medium text-[var(--color-text-primary)]">
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

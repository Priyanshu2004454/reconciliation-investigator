"use client";

import { useState, useRef } from "react";
import { AppShell } from "@/components/AppShell";
import { PageHeader, Card, ErrorState, Button, EmptyState } from "@/components/ui";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { ImportSummary } from "@/lib/types";

export default function BankStatementsPage() {
  const { merchantAccount } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setSummary(null);
    try {
      const result = await api.uploadBankStatement(file);
      setSummary(result);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <AppShell>
      <PageHeader
        title="Bank Statements"
        description="Upload a bank statement CSV to match against Razorpay settlements. Column names are auto-detected."
      />

      {!merchantAccount ? (
        <EmptyState
          title="No merchant account connected yet"
          description="Connect your Razorpay Test Mode account in Settings first."
        />
      ) : (
        <>
          <Card className="p-5">
            <div className="flex items-center gap-3">
              <input
                ref={inputRef}
                type="file"
                accept=".csv"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="flex-1 text-sm text-[var(--color-text-secondary)] file:mr-3 file:rounded-sm file:border file:border-[var(--color-border-strong)] file:bg-transparent file:px-3 file:py-1.5 file:text-xs file:text-[var(--color-text-primary)]"
              />
              <Button onClick={handleUpload} disabled={!file || uploading}>
                {uploading ? "Uploading…" : "Upload"}
              </Button>
            </div>
            <p className="mt-3 text-xs text-[var(--color-text-muted)]">
              Expected columns (any naming variant): date, reference/UTR, description, credit, debit, balance.
            </p>
          </Card>

          {error && (
            <div className="mt-4">
              <ErrorState message={error} />
            </div>
          )}

          {summary && (
            <div className="mt-6 space-y-4">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <SummaryTile label="Rows Imported" value={summary.rows_imported} accent="var(--color-matched)" />
                <SummaryTile label="Rows Rejected" value={summary.rows_rejected} accent="var(--color-critical)" />
                <SummaryTile label="Duplicated" value={summary.rows_duplicated} accent="var(--color-review)" />
                <SummaryTile label="Needs Review" value={summary.rows_requiring_review} accent="var(--color-review)" />
              </div>

              <Card className="p-5">
                <div className="mb-3 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  Detected Column Mapping
                </div>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                  {Object.entries(summary.detected_columns).map(([field, original]) => (
                    <div key={field} className="font-mono text-xs">
                      <span className="text-[var(--color-text-muted)]">{field}</span>
                      <span className="mx-1.5 text-[var(--color-text-muted)]">←</span>
                      <span className="text-[var(--color-text-primary)]">{original}</span>
                    </div>
                  ))}
                </div>
              </Card>

              {summary.errors.length > 0 && (
                <Card className="p-5">
                  <div className="mb-3 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                    Row Errors
                  </div>
                  <div className="space-y-1.5">
                    {summary.errors.slice(0, 20).map((e, i) => (
                      <div key={i} className="font-mono text-xs text-[var(--color-critical)]">
                        Row {e.row_number}: {e.reason}
                      </div>
                    ))}
                    {summary.errors.length > 20 && (
                      <div className="text-xs text-[var(--color-text-muted)]">
                        …and {summary.errors.length - 20} more.
                      </div>
                    )}
                  </div>
                </Card>
              )}
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}

function SummaryTile({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-1 font-mono text-xl tabular font-semibold" style={{ color: accent }}>
        {value}
      </div>
    </div>
  );
}

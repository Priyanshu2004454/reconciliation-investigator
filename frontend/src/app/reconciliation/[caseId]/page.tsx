"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { PageHeader, Card, LoadingState, ErrorState, Button } from "@/components/ui";
import { StatusStamp } from "@/components/StatusStamp";
import { ConfidenceGauge } from "@/components/ConfidenceGauge";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { ReconciliationCaseDetail, Investigation } from "@/lib/types";

function formatRupees(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function MetricField({
  label,
  value,
  subvalue,
  mono = false,
  accent,
}: {
  label: string;
  value: string;
  subvalue?: string;
  mono?: boolean;
  accent?: string;
}) {
  return (
    <div className="space-y-0.5">
      <div className="text-[11px] font-medium text-[var(--color-text-muted)]">{label}</div>
      <div
        className={`text-[13px] font-medium ${mono ? "tabular" : ""}`}
        style={{ color: accent ?? "var(--color-text-primary)" }}
      >
        {value}
      </div>
      {subvalue && <div className="text-[11px] text-[var(--color-text-secondary)]">{subvalue}</div>}
    </div>
  );
}

function Disclosure({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-[var(--color-border)] pt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-primary)] hover:underline"
      >
        <span className={`inline-block transition-transform ${open ? "rotate-90" : ""}`}>›</span>
        {open ? `Hide ${label.toLowerCase()}` : label}
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  );
}

export default function CaseDetailPage() {
  const params = useParams<{ caseId: string }>();
  const router = useRouter();
  const caseId = params.caseId;

  const [caseDetail, setCaseDetail] = useState<ReconciliationCaseDetail | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [investigating, setInvestigating] = useState(false);
  const [investigateError, setInvestigateError] = useState<string | null>(null);
  const [investigationStep, setInvestigationStep] = useState(0);

  const [decisionBusy, setDecisionBusy] = useState<string | null>(null);
  const [decisionNotes, setDecisionNotes] = useState("");
  const [decisionSuccess, setDecisionSuccess] = useState<string | null>(null);
  const [isEditingDecision, setIsEditingDecision] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, inv] = await Promise.all([api.getCase(caseId), api.getLatestInvestigation(caseId)]);
      setCaseDetail(c);
      setInvestigation(inv);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load case.");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  // Stepped progress indicator during active investigation
  useEffect(() => {
    if (!investigating) {
      setInvestigationStep(0);
      return;
    }
    setInvestigationStep(1);
    const t1 = setTimeout(() => setInvestigationStep(2), 1200);
    const t2 = setTimeout(() => setInvestigationStep(3), 2600);
    const t3 = setTimeout(() => setInvestigationStep(4), 4200);
    const t4 = setTimeout(() => setInvestigationStep(5), 5800);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
    };
  }, [investigating]);

  const handleInvestigate = async () => {
    setInvestigating(true);
    setInvestigateError(null);
    setDecisionSuccess(null);
    try {
      const result = await api.triggerInvestigation(caseId);
      setInvestigation(result);
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 503) {
          setInvestigateError(
            err.message ||
              "AI Investigator is not configured. Please check your backend AI provider settings (AI_PROVIDER, API key) and restart the backend."
          );
        } else {
          setInvestigateError(err.message);
        }
      } else {
        setInvestigateError("Investigation failed. Please check your backend connection.");
      }
    } finally {
      setInvestigating(false);
    }
  };

  const handleDecision = async (decision: "RESOLVED" | "NEEDS_REVIEW" | "REJECTED") => {
    if (!investigation) return;
    setDecisionBusy(decision);
    setInvestigateError(null);
    setDecisionSuccess(null);
    try {
      const updated = await api.submitDecision(investigation.id, decision, decisionNotes || undefined);
      setInvestigation(updated);
      setDecisionSuccess(`Decision recorded: ${decision}. Case status updated.`);
      setIsEditingDecision(false);
      await load();
    } catch (err) {
      setInvestigateError(err instanceof ApiError ? err.message : "Failed to record decision.");
    } finally {
      setDecisionBusy(null);
    }
  };

  if (loading) {
    return (
      <AppShell>
        <LoadingState label="Loading reconciliation workspace…" />
      </AppShell>
    );
  }

  if (error || !caseDetail) {
    return (
      <AppShell>
        <div className="space-y-4">
          <Link
            href="/reconciliation"
            className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          >
            ← Back to Reconciliation
          </Link>
          <ErrorState message={error ?? "Case not found."} />
        </div>
      </AppShell>
    );
  }

  const hasDifference = (caseDetail.difference ?? 0) !== 0;

  return (
    <AppShell>
      {/* Navigation breadcrumb */}
      <div className="mb-4 flex items-center justify-between">
        <Link
          href="/reconciliation"
          className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
        >
          ← Back to Reconciliation
        </Link>
        <div className="text-xs text-[var(--color-text-muted)]">
          Case ID: <span className="text-[var(--color-text-secondary)]">{caseDetail.id.slice(0, 8)}</span>
        </div>
      </div>

      {/* Case Header */}
      <PageHeader
        title={caseDetail.razorpay_settlement_id ?? `Case ${caseDetail.id.slice(0, 8)}`}
        description={`Opened ${formatDate(caseDetail.created_at)} · Last reconciled ${formatDate(caseDetail.updated_at)}`}
        action={
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-[11px] font-medium text-[var(--color-text-muted)]">Case Status</div>
              <div className="mt-1"><StatusStamp status={caseDetail.status} /></div>
            </div>
            {investigation && (
              <div className="text-right">
                <div className="text-[11px] font-medium text-[var(--color-text-muted)]">AI Finding</div>
                <div className="mt-1">
                  <span className="inline-flex items-center gap-1 rounded-full bg-[var(--color-ai-accent-bg)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-ai-accent)]">
                    ✦ {investigation.root_cause.replace(/_/g, " ")}
                  </span>
                </div>
              </div>
            )}
          </div>
        }
      />

      {decisionSuccess && (
        <div className="mb-6 rounded-lg border border-green-200 bg-[var(--color-matched-bg)] px-4 py-3 text-sm font-medium text-[var(--color-matched)]">
          ✓ {decisionSuccess}
        </div>
      )}

      {/* Financial Discrepancy Overview */}
      <Card className="mb-6 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Financial Summary</h2>
          {caseDetail.match_rule && (
            <span className="rounded-full bg-[var(--color-bg)] px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">
              Rule: {caseDetail.match_rule}
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-lg bg-[var(--color-bg)] p-4">
            <div className="text-[11px] font-medium text-[var(--color-text-muted)]">Expected Amount</div>
            <div className="mt-1 text-xl font-semibold tabular text-[var(--color-text-primary)]">
              {formatRupees(caseDetail.expected_amount)}
            </div>
            <div className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">Gross - Fees - Taxes</div>
          </div>

          <div className="rounded-lg bg-[var(--color-bg)] p-4">
            <div className="text-[11px] font-medium text-[var(--color-text-muted)]">Actual Amount</div>
            <div className="mt-1 text-xl font-semibold tabular text-[var(--color-text-primary)]">
              {formatRupees(caseDetail.actual_amount)}
            </div>
            <div className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">Bank statement credit</div>
          </div>

          <div className={`rounded-lg p-4 ${hasDifference ? "bg-[var(--color-critical-bg)]" : "bg-[var(--color-matched-bg)]"}`}>
            <div className="text-[11px] font-medium" style={{ color: hasDifference ? "var(--color-critical)" : "var(--color-matched)" }}>
              Difference
            </div>
            <div className="mt-1 text-xl font-semibold tabular" style={{ color: hasDifference ? "var(--color-critical)" : "var(--color-matched)" }}>
              {formatRupees(caseDetail.difference)}
            </div>
            <div className="mt-0.5 text-[11px]" style={{ color: hasDifference ? "var(--color-critical)" : "var(--color-matched)" }}>
              {hasDifference ? "Requires resolution" : "Exact match"}
            </div>
          </div>

          <div className="rounded-lg bg-[var(--color-bg)] p-4">
            <div className="text-[11px] font-medium text-[var(--color-text-muted)]">Identifiers</div>
            <div className="mt-1 truncate text-xs text-[var(--color-text-primary)]" title={caseDetail.razorpay_settlement_id ?? "—"}>
              S: {caseDetail.razorpay_settlement_id ?? "—"}
            </div>
            <div className="mt-0.5 truncate text-xs text-[var(--color-text-secondary)]" title={caseDetail.razorpay_payment_id ?? "—"}>
              P: {caseDetail.razorpay_payment_id ?? "—"}
            </div>
          </div>
        </div>
      </Card>

      {/* Multi-Source Evidence Sections */}
      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">Razorpay Settlement</span>
            <span className="text-[11px] text-[var(--color-text-muted)]">Razorpay API</span>
          </div>
          <div className="space-y-3.5">
            <MetricField label="Settlement ID" value={caseDetail.razorpay_settlement_id ?? "—"} mono />
            <MetricField
              label="Settlement UTR"
              value={caseDetail.settlement_details?.utr ?? "—"}
              subvalue={caseDetail.settlement_details?.utr ? "Bank reference" : undefined}
              mono
            />
            <div className="grid grid-cols-2 gap-2">
              <MetricField label="Gross Amount" value={formatRupees(caseDetail.settlement_details?.amount)} mono />
              <MetricField label="Status" value={caseDetail.settlement_details?.status ?? "—"} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <MetricField label="Fees Deducted" value={formatRupees(caseDetail.settlement_details?.fees)} mono />
              <MetricField label="Tax Deducted" value={formatRupees(caseDetail.settlement_details?.tax)} mono />
            </div>
            <MetricField label="Settlement Date" value={formatDate(caseDetail.settlement_details?.settlement_date)} />
          </div>
        </Card>

        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">Razorpay Payment</span>
            <span className="text-[11px] text-[var(--color-text-muted)]">Razorpay API</span>
          </div>
          {caseDetail.razorpay_payment_id ? (
            <div className="space-y-3.5">
              <MetricField label="Payment ID" value={caseDetail.razorpay_payment_id} mono />
              <div className="grid grid-cols-2 gap-2">
                <MetricField label="Payment Amount" value={formatRupees(caseDetail.payment_details?.amount)} mono />
                <MetricField label="Method" value={caseDetail.payment_details?.method?.toUpperCase() ?? "UPI"} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <MetricField label="Fee" value={formatRupees(caseDetail.payment_details?.fee)} mono />
                <MetricField label="Tax" value={formatRupees(caseDetail.payment_details?.tax)} mono />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <MetricField label="Status" value={caseDetail.payment_details?.status ?? "captured"} />
                <MetricField label="Payment Date" value={formatDate(caseDetail.payment_details?.payment_date)} />
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-xs leading-relaxed text-[var(--color-text-muted)]">
              No direct payment ID was linked to this settlement record.
            </div>
          )}
        </Card>

        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">Bank Statement</span>
            <span className="text-[11px] text-[var(--color-text-muted)]">Bank Feed</span>
          </div>
          {caseDetail.bank_transaction_id ? (
            <div className="space-y-3.5">
              <MetricField label="Bank Row ID" value={caseDetail.bank_transaction_id.slice(0, 16) + "…"} mono />
              <MetricField
                label="Bank UTR / Ref"
                value={caseDetail.bank_transaction_details?.utr ?? caseDetail.bank_transaction_details?.reference_id ?? "—"}
                mono
              />
              <div className="grid grid-cols-2 gap-2">
                <MetricField label="Credit Amount" value={formatRupees(caseDetail.bank_transaction_details?.credit)} mono accent="var(--color-matched)" />
                <MetricField label="Debit Amount" value={formatRupees(caseDetail.bank_transaction_details?.debit)} mono />
              </div>
              <MetricField label="Transaction Date" value={formatDate(caseDetail.bank_transaction_details?.transaction_date)} />
              <MetricField label="Statement Narration" value={caseDetail.bank_transaction_details?.description ?? "—"} />
            </div>
          ) : (
            <div className="py-8 text-center text-xs leading-relaxed text-[var(--color-critical)]">
              No matching bank transaction found in uploaded bank statements.
            </div>
          )}
        </Card>
      </div>

      {caseDetail.refunds && caseDetail.refunds.length > 0 && (
        <Card className="mb-6 p-5">
          <div className="mb-3 text-[13px] font-semibold text-[var(--color-text-primary)]">
            Associated Refunds ({caseDetail.refunds.length})
          </div>
          <div className="divide-y divide-[var(--color-border)]">
            {caseDetail.refunds.map((ref) => (
              <div key={ref.id} className="grid grid-cols-4 py-2.5 text-[13px]">
                <span className="tabular text-[var(--color-text-primary)]">{ref.razorpay_refund_id}</span>
                <span className="tabular font-medium text-[var(--color-review)]">{formatRupees(ref.amount)}</span>
                <span className="text-[var(--color-text-secondary)]">{ref.status}</span>
                <span className="text-right text-[var(--color-text-muted)]">{formatDate(ref.refund_date)}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* AI Investigator */}
      <Card className="p-6">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-ai-accent)]">
              <span>✦</span> AI Investigator
            </div>
            <h2 className="mt-0.5 text-base font-semibold text-[var(--color-text-primary)]">
              Automated Root-Cause Analysis
            </h2>
          </div>
          <Button onClick={handleInvestigate} disabled={investigating}>
            {investigating ? (
              <span className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Investigating…
              </span>
            ) : investigation ? (
              "Re-investigate with AI ✦"
            ) : (
              "Investigate with AI ✦"
            )}
          </Button>
        </div>

        {investigateError && (
          <div className="mb-4">
            <ErrorState message={investigateError} />
          </div>
        )}

        {investigating && (
          <div className="space-y-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4 text-[13px]">
            <div className={`flex items-center gap-2 ${investigationStep >= 1 ? "text-[var(--color-text-primary)]" : "text-[var(--color-text-muted)]"}`}>
              <span>{investigationStep >= 1 ? "✓" : "○"}</span> Payment checked
            </div>
            <div className={`flex items-center gap-2 ${investigationStep >= 2 ? "text-[var(--color-text-primary)]" : "text-[var(--color-text-muted)]"}`}>
              <span>{investigationStep >= 2 ? "✓" : "○"}</span> Settlement checked
            </div>
            <div className={`flex items-center gap-2 ${investigationStep >= 3 ? "text-[var(--color-text-primary)]" : "text-[var(--color-text-muted)]"}`}>
              <span>{investigationStep >= 3 ? "✓" : investigationStep >= 3 ? "◉" : "○"}</span> Comparing bank evidence
            </div>
            <div className={`flex items-center gap-2 ${investigationStep >= 4 ? "text-[var(--color-text-primary)]" : "text-[var(--color-text-muted)]"}`}>
              <span>{investigationStep >= 4 ? "✓" : "○"}</span> Verifying fee &amp; tax arithmetic
            </div>
            <div className={`flex items-center gap-2 ${investigationStep >= 5 ? "text-[var(--color-ai-accent)]" : "text-[var(--color-text-muted)]"}`}>
              <span>{investigationStep >= 5 ? "◉" : "○"}</span> Determining root cause
            </div>
          </div>
        )}

        {!investigating && !investigation && (
          <div className="py-10 text-center">
            <div className="mx-auto max-w-md space-y-1.5">
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                No investigation has been run for this case yet.
              </p>
              <p className="text-sm text-[var(--color-text-secondary)]">
                Click &quot;Investigate with AI&quot; for an evidence-backed root-cause analysis.
              </p>
            </div>
          </div>
        )}

        {!investigating && investigation && (
          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-4 rounded-lg bg-[var(--color-bg)] p-4 sm:grid-cols-3">
              <div>
                <div className="text-[11px] font-medium text-[var(--color-text-muted)]">Root Cause</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <StatusStamp status={investigation.classification} />
                  <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-[var(--color-text-primary)]">
                    {investigation.root_cause.replace(/_/g, " ")}
                  </span>
                </div>
              </div>
              <div>
                <div className="mb-1.5 text-[11px] font-medium text-[var(--color-text-muted)]">Confidence</div>
                <ConfidenceGauge value={investigation.confidence} />
              </div>
              <div>
                <div className="text-[11px] font-medium text-[var(--color-text-muted)]">Difference</div>
                <div className="mt-1.5 text-lg font-semibold tabular text-[var(--color-critical)]">
                  {formatRupees(caseDetail.difference)}
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border-strong)] bg-white p-4 text-sm font-medium text-[var(--color-text-primary)]">
              <div className="flex items-start gap-2">
                <span className="text-[var(--color-primary)]">→</span>
                <span>{investigation.recommended_action}</span>
              </div>
            </div>

            <Disclosure label="View reasoning">
              <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">{investigation.explanation}</p>
            </Disclosure>

            {investigation.evidence.length > 0 && (
              <Disclosure label={`View evidence (${investigation.evidence.length})`}>
                <div className="space-y-2">
                  {investigation.evidence.map((e, idx) => (
                    <div key={idx} className="rounded-lg border border-[var(--color-border)] p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-medium text-[var(--color-ai-accent)]">
                          {e.source_type.replace(/_/g, " ")}
                        </span>
                        <span className="text-[11px] tabular text-[var(--color-text-muted)]">{e.source_id}</span>
                      </div>
                      <div className="mt-1 text-xs leading-relaxed text-[var(--color-text-secondary)]">
                        {e.description}
                      </div>
                    </div>
                  ))}
                </div>
              </Disclosure>
            )}

            <div className="border-t border-[var(--color-border)] pt-5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-[13px] font-semibold text-[var(--color-text-primary)]">Human Review</h3>
                {investigation.human_decision && !isEditingDecision && (
                  <Button variant="secondary" onClick={() => setIsEditingDecision(true)}>
                    Change Decision
                  </Button>
                )}
              </div>

              {investigation.human_decision && !isEditingDecision ? (
                <div className="rounded-lg bg-[var(--color-bg)] p-4">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-[var(--color-text-muted)]">Decision:</span>
                    <StatusStamp status={investigation.human_decision} />
                  </div>
                  {investigation.human_notes && (
                    <div className="mt-2 text-xs text-[var(--color-text-secondary)]">
                      <span className="text-[var(--color-text-muted)]">Notes:</span> {investigation.human_notes}
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-3 rounded-lg bg-[var(--color-bg)] p-4">
                  <input
                    value={decisionNotes}
                    onChange={(e) => setDecisionNotes(e.target.value)}
                    placeholder="Optional notes for audit trail…"
                    className="w-full rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-primary)]"
                  />
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <Button onClick={() => handleDecision("RESOLVED")} disabled={decisionBusy !== null}>
                      {decisionBusy === "RESOLVED" ? "Saving…" : "Resolve"}
                    </Button>
                    <Button variant="secondary" onClick={() => handleDecision("NEEDS_REVIEW")} disabled={decisionBusy !== null}>
                      {decisionBusy === "NEEDS_REVIEW" ? "Saving…" : "Needs Review"}
                    </Button>
                    <Button variant="danger" onClick={() => handleDecision("REJECTED")} disabled={decisionBusy !== null}>
                      {decisionBusy === "REJECTED" ? "Saving…" : "Reject Finding"}
                    </Button>
                    {isEditingDecision && (
                      <button
                        type="button"
                        onClick={() => setIsEditingDecision(false)}
                        className="ml-2 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </Card>
    </AppShell>
  );
}

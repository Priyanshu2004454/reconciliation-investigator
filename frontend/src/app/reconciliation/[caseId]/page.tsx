"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { PageHeader, Card, LoadingState, ErrorState, Button } from "@/components/ui";
import { StatusStamp } from "@/components/StatusStamp";
import { ConfidenceGauge } from "@/components/ConfidenceGauge";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { ReconciliationCaseDetail, Investigation } from "@/lib/types";

function formatRupees(n: number | null): string {
  if (n === null) return "—";
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-0.5 font-mono text-sm tabular text-[var(--color-text-primary)]">{value}</div>
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
  const [decisionBusy, setDecisionBusy] = useState<string | null>(null);
  const [decisionNotes, setDecisionNotes] = useState("");

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

  const handleInvestigate = async () => {
    setInvestigating(true);
    setInvestigateError(null);
    try {
      const result = await api.triggerInvestigation(caseId);
      setInvestigation(result);
    } catch (err) {
      setInvestigateError(err instanceof ApiError ? err.message : "Investigation failed.");
    } finally {
      setInvestigating(false);
    }
  };

  const handleDecision = async (decision: "RESOLVED" | "NEEDS_REVIEW" | "REJECTED") => {
    if (!investigation) return;
    setDecisionBusy(decision);
    try {
      const updated = await api.submitDecision(investigation.id, decision, decisionNotes || undefined);
      setInvestigation(updated);
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
        <LoadingState label="Loading case…" />
      </AppShell>
    );
  }

  if (error || !caseDetail) {
    return (
      <AppShell>
        <ErrorState message={error ?? "Case not found."} />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <button
        onClick={() => router.push("/reconciliation")}
        className="mb-4 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
      >
        ← Back to Reconciliation
      </button>

      <PageHeader
        title={caseDetail.razorpay_settlement_id ?? caseDetail.id}
        description={`Case opened ${new Date(caseDetail.created_at).toLocaleString("en-IN")}`}
        action={<StatusStamp status={caseDetail.status} />}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-4 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
            Transaction
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Payment ID" value={caseDetail.razorpay_payment_id ?? "—"} />
            <Field label="Settlement ID" value={caseDetail.razorpay_settlement_id ?? "—"} />
            <Field label="Expected Amount" value={formatRupees(caseDetail.expected_amount)} />
            <Field label="Actual Amount" value={formatRupees(caseDetail.actual_amount)} />
            <Field label="Difference" value={formatRupees(caseDetail.difference)} />
            <Field label="Match Rule" value={caseDetail.match_rule ?? "—"} />
          </div>
        </Card>

        <Card className="p-5">
          <div className="mb-4 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
            Bank
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field
              label="Matched Transaction"
              value={caseDetail.bank_transaction_id ? caseDetail.bank_transaction_id.slice(0, 8) : "No match"}
            />
            <Field label="Last Updated" value={new Date(caseDetail.updated_at).toLocaleString("en-IN")} />
          </div>
        </Card>
      </div>

      <div className="mt-6">
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">AI Finding</div>
            <Button onClick={handleInvestigate} disabled={investigating}>
              {investigating ? "Investigating…" : investigation ? "Re-investigate" : "Investigate"}
            </Button>
          </div>

          {investigateError && <ErrorState message={investigateError} />}

          {investigating && (
            <div className="space-y-1.5 py-4 font-mono text-xs text-[var(--color-text-secondary)]">
              <div>→ Loading reconciliation case…</div>
              <div>→ Fetching payment, settlement, refund history…</div>
              <div>→ Searching bank statement…</div>
              <div>→ Comparing evidence and calculating expected settlement…</div>
              <div>→ Determining root cause…</div>
            </div>
          )}

          {!investigating && !investigation && (
            <div className="py-6 text-center text-sm text-[var(--color-text-secondary)]">
              No investigation has been run for this case yet.
            </div>
          )}

          {!investigating && investigation && (
            <div className="space-y-5">
              <div className="flex items-center gap-4">
                <StatusStamp status={investigation.classification} />
                <span className="font-mono text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  {investigation.root_cause.replace(/_/g, " ")}
                </span>
              </div>

              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  Explanation
                </div>
                <p className="text-sm leading-relaxed text-[var(--color-text-primary)]">{investigation.explanation}</p>
              </div>

              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  Confidence
                </div>
                <ConfidenceGauge value={investigation.confidence} />
              </div>

              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  Recommended Action
                </div>
                <p className="text-sm text-[var(--color-text-primary)]">{investigation.recommended_action}</p>
              </div>

              {investigation.evidence.length > 0 && (
                <div>
                  <div className="mb-2 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                    Evidence Chain
                  </div>
                  <div className="space-y-0 border-l border-[var(--color-border-strong)] pl-4">
                    {investigation.evidence.map((e, i) => (
                      <div key={i} className="relative pb-4 last:pb-0">
                        <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-[var(--color-explained)]" />
                        <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                          {e.source_type.replace(/_/g, " ")} · {e.source_id}
                        </div>
                        <div className="mt-0.5 text-xs text-[var(--color-text-secondary)]">{e.description}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="border-t border-[var(--color-border)] pt-4">
                <div className="mb-2 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  Human Decision
                </div>
                {investigation.human_decision ? (
                  <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                    Decision recorded: <StatusStamp status={investigation.human_decision} />
                  </div>
                ) : (
                  <div className="space-y-3">
                    <input
                      value={decisionNotes}
                      onChange={(e) => setDecisionNotes(e.target.value)}
                      placeholder="Optional notes…"
                      className="w-full rounded-sm border border-[var(--color-border-strong)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-explained)]"
                    />
                    <div className="flex gap-2">
                      <Button onClick={() => handleDecision("RESOLVED")} disabled={decisionBusy !== null}>
                        {decisionBusy === "RESOLVED" ? "Saving…" : "Mark Resolved"}
                      </Button>
                      <Button variant="secondary" onClick={() => handleDecision("NEEDS_REVIEW")} disabled={decisionBusy !== null}>
                        {decisionBusy === "NEEDS_REVIEW" ? "Saving…" : "Needs Human Review"}
                      </Button>
                      <Button variant="danger" onClick={() => handleDecision("REJECTED")} disabled={decisionBusy !== null}>
                        {decisionBusy === "REJECTED" ? "Saving…" : "Reject Finding"}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  );
}

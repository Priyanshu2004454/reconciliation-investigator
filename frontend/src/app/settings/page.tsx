"use client";

import { useEffect, useState, FormEvent } from "react";
import { AppShell } from "@/components/AppShell";
import { PageHeader, Card, ErrorState, Button, LoadingState } from "@/components/ui";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { HealthCheck } from "@/lib/types";

function StatusPill({ ok, okLabel, notOkLabel }: { ok: boolean; okLabel: string; notOkLabel: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-medium"
      style={{
        color: ok ? "var(--color-matched)" : "var(--color-critical)",
        backgroundColor: ok ? "var(--color-matched-bg)" : "var(--color-critical-bg)",
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: ok ? "var(--color-matched)" : "var(--color-critical)" }} />
      {ok ? okLabel : notOkLabel}
    </span>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="-mx-2 flex items-center justify-between rounded-lg px-2 py-1.5 transition-colors hover:bg-[var(--color-surface-hover)]">
      <span className="text-[13px] text-[var(--color-text-secondary)]">{label}</span>
      <span className="text-[13px] font-medium text-[var(--color-text-primary)]">{value}</span>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="mb-4 text-[13px] font-semibold tracking-tight text-[var(--color-text-primary)]">{children}</div>;
}

export default function SettingsPage() {
  const { user, merchantAccount, refreshMerchantAccount } = useAuth();
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [businessName, setBusinessName] = useState("");
  const [keyId, setKeyId] = useState("");
  const [isTestMode, setIsTestMode] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setHealth(await api.getHealth());
      } catch (err) {
        setHealthError(err instanceof ApiError ? err.message : "Cannot reach backend.");
      } finally {
        setLoadingHealth(false);
      }
    })();
  }, []);

  const handleCreateAccount = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await api.createMerchantAccount(businessName, keyId, isTestMode);
      await refreshMerchantAccount();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to create merchant account.");
    } finally {
      setSubmitting(false);
    }
  };

  const razorpayConfigured = !!health?.config.RAZORPAY_KEY_ID && health.config.RAZORPAY_KEY_ID !== "rzp_test_x...";

  // Provider-aware: AI_PROVIDER can be "anthropic" or "gemini", each with its
  // own key field on the health config -- check whichever one is active.
  const aiProvider = health?.config.AI_PROVIDER ?? "anthropic";
  const aiConfigured =
    aiProvider === "gemini"
      ? health?.config.GEMINI_API_KEY === "***REDACTED***"
      : health?.config.ANTHROPIC_API_KEY === "***REDACTED***";

  return (
    <AppShell>
      <PageHeader title="Settings" description="Merchant connection and backend integration status." />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card className="p-6">
          <SectionTitle>Account</SectionTitle>
          <div className="space-y-0.5">
            <InfoRow label="Email" value={user?.email} />
            <InfoRow label="Name" value={user?.full_name} />
          </div>
        </Card>

        <Card className="p-6">
          <SectionTitle>Backend Connection</SectionTitle>
          {loadingHealth && <LoadingState label="Checking backend…" />}
          {healthError && <ErrorState message={healthError} />}
          {health && (
            <div className="space-y-0.5">
              <InfoRow label="API server" value={<StatusPill ok={health.status === "ok"} okLabel={health.app_env} notOkLabel="Unreachable" />} />
              <InfoRow
                label="Razorpay Test Mode key"
                value={<StatusPill ok={razorpayConfigured} okLabel="Configured" notOkLabel="Not set" />}
              />
              <InfoRow
                label={`AI Investigator (${aiProvider === "gemini" ? "Gemini" : "Claude"})`}
                value={
                  <StatusPill
                    ok={aiConfigured}
                    okLabel={`Configured · ${health.config.AI_MODEL}`}
                    notOkLabel="Not set"
                  />
                }
              />
            </div>
          )}
        </Card>
      </div>

      <div className="mt-5">
        <Card className="p-6">
          <SectionTitle>Razorpay Merchant Account</SectionTitle>

          {merchantAccount ? (
            <div className="space-y-0.5">
              <InfoRow label="Business name" value={merchantAccount.business_name} />
              <InfoRow label="Key ID" value={<span className="tabular text-xs">{merchantAccount.razorpay_key_id}</span>} />
              <InfoRow label="Mode" value={merchantAccount.is_test_mode ? "Test Mode" : "Live Mode"} />
            </div>
          ) : (
            <form onSubmit={handleCreateAccount} className="space-y-4">
              <p className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                Only your public Razorpay Key ID is stored here. The secret key always stays in the backend&apos;s
                environment variables and is never sent from this form.
              </p>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                  Business name
                </label>
                <input
                  required
                  value={businessName}
                  onChange={(e) => setBusinessName(e.target.value)}
                  className="w-full rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-primary)]"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                  Razorpay Key ID (public)
                </label>
                <input
                  required
                  placeholder="rzp_test_..."
                  value={keyId}
                  onChange={(e) => setKeyId(e.target.value)}
                  className="w-full rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-primary)]"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                <input type="checkbox" checked={isTestMode} onChange={(e) => setIsTestMode(e.target.checked)} />
                Test Mode
              </label>
              {formError && <ErrorState message={formError} />}
              <Button type="submit" disabled={submitting}>
                {submitting ? "Connecting…" : "Connect Account"}
              </Button>
            </form>
          )}
        </Card>
      </div>
    </AppShell>
  );
}

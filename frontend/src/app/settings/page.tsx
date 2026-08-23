"use client";

import { useEffect, useState, FormEvent } from "react";
import { AppShell } from "@/components/AppShell";
import { PageHeader, Card, ErrorState, Button, LoadingState } from "@/components/ui";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { HealthCheck } from "@/lib/types";

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{ backgroundColor: ok ? "var(--color-matched)" : "var(--color-critical)" }}
    />
  );
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
  const aiConfigured = health?.config.ANTHROPIC_API_KEY === "***REDACTED***";

  return (
    <AppShell>
      <PageHeader title="Settings" description="Merchant connection and backend integration status." />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-4 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Account</div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-[var(--color-text-secondary)]">Email</span>
              <span className="font-mono text-[var(--color-text-primary)]">{user?.email}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--color-text-secondary)]">Name</span>
              <span className="text-[var(--color-text-primary)]">{user?.full_name}</span>
            </div>
          </div>
        </Card>

        <Card className="p-5">
          <div className="mb-4 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
            Backend Connection
          </div>
          {loadingHealth && <LoadingState label="Checking backend…" />}
          {healthError && <ErrorState message={healthError} />}
          {health && (
            <div className="space-y-2.5 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-secondary)]">API server</span>
                <span className="flex items-center gap-2 font-mono text-xs text-[var(--color-text-primary)]">
                  <StatusDot ok={health.status === "ok"} /> {health.app_env}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-secondary)]">Razorpay Test Mode key</span>
                <span className="flex items-center gap-2 font-mono text-xs text-[var(--color-text-primary)]">
                  <StatusDot ok={razorpayConfigured} /> {razorpayConfigured ? "Configured" : "Not set"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-secondary)]">AI Investigator (Claude)</span>
                <span className="flex items-center gap-2 font-mono text-xs text-[var(--color-text-primary)]">
                  <StatusDot ok={aiConfigured} /> {aiConfigured ? `Configured (${health.config.AI_MODEL})` : "Not set"}
                </span>
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="mt-6">
        <Card className="p-5">
          <div className="mb-4 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
            Razorpay Merchant Account
          </div>

          {merchantAccount ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[var(--color-text-secondary)]">Business name</span>
                <span className="text-[var(--color-text-primary)]">{merchantAccount.business_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-secondary)]">Key ID</span>
                <span className="font-mono text-xs text-[var(--color-text-primary)]">{merchantAccount.razorpay_key_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-secondary)]">Mode</span>
                <span className="text-[var(--color-text-primary)]">
                  {merchantAccount.is_test_mode ? "Test Mode" : "Live Mode"}
                </span>
              </div>
            </div>
          ) : (
            <form onSubmit={handleCreateAccount} className="space-y-3">
              <p className="text-xs text-[var(--color-text-secondary)]">
                Only your public Razorpay Key ID is stored here. The secret key always stays in the backend&apos;s
                environment variables and is never sent from this form.
              </p>
              <div>
                <label className="mb-1 block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  Business name
                </label>
                <input
                  required
                  value={businessName}
                  onChange={(e) => setBusinessName(e.target.value)}
                  className="w-full rounded-sm border border-[var(--color-border-strong)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-explained)]"
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  Razorpay Key ID (public)
                </label>
                <input
                  required
                  placeholder="rzp_test_..."
                  value={keyId}
                  onChange={(e) => setKeyId(e.target.value)}
                  className="w-full rounded-sm border border-[var(--color-border-strong)] bg-[var(--color-bg)] px-3 py-2 font-mono text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-explained)]"
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

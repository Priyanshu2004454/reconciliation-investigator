"use client";

import { useState, FormEvent } from "react";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui";

export default function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, fullName);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="font-mono text-sm font-semibold tracking-tight text-[var(--color-text-primary)]">
            RECON<span className="text-[var(--color-explained)]">/</span>INVESTIGATOR
          </div>
          <div className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Razorpay AI Buildathon 2026
          </div>
        </div>

        <div className="rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-5 flex gap-4 border-b border-[var(--color-border)]">
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`pb-3 text-[13px] font-medium ${
                  mode === m
                    ? "border-b-2 border-[var(--color-explained)] text-[var(--color-text-primary)]"
                    : "text-[var(--color-text-muted)]"
                }`}
              >
                {m === "login" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>

          <form onSubmit={onSubmit} className="space-y-3">
            {mode === "register" && (
              <div>
                <label className="mb-1 block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  Full name
                </label>
                <input
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full rounded-sm border border-[var(--color-border-strong)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-explained)]"
                />
              </div>
            )}
            <div>
              <label className="mb-1 block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Email
              </label>
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-sm border border-[var(--color-border-strong)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-explained)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Password
              </label>
              <input
                required
                type="password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-sm border border-[var(--color-border-strong)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-explained)]"
              />
            </div>

            {error && (
              <div className="rounded-sm border border-[var(--color-critical)] bg-[var(--color-critical-bg)] px-3 py-2 text-xs text-[var(--color-critical)]">
                {error}
              </div>
            )}

            <div className="pt-2">
              <Button type="submit" disabled={busy}>
                {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

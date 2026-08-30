"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PageHeader, Card, LoadingState, ErrorState, EmptyState } from "@/components/ui";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { AuditLogEntry } from "@/lib/types";

const ACTOR_COLORS: Record<string, string> = {
  AI: "var(--color-ai-accent)",
  HUMAN: "var(--color-matched)",
  SYSTEM: "var(--color-text-muted)",
};

const ACTOR_BG: Record<string, string> = {
  AI: "var(--color-ai-accent-bg)",
  HUMAN: "var(--color-matched-bg)",
  SYSTEM: "var(--color-surface-hover)",
};

export default function AuditLogPage() {
  const { merchantAccount } = useAuth();
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!merchantAccount) {
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const data = await api.listAuditLogs(undefined, 200);
        setLogs(data);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load audit log.");
      } finally {
        setLoading(false);
      }
    })();
  }, [merchantAccount]);

  return (
    <AppShell>
      <PageHeader
        title="Reports"
        description="Every AI and human action, in order. This trail is immutable from the UI."
      />

      {!merchantAccount && (
        <EmptyState title="No merchant account connected yet" description="Connect one in Settings first." />
      )}

      {merchantAccount && loading && <LoadingState label="Loading audit trail…" />}
      {merchantAccount && error && <ErrorState message={error} />}

      {merchantAccount && !loading && !error && logs.length === 0 && (
        <EmptyState title="No activity yet" description="Actions will appear here as reconciliation and investigation runs happen." />
      )}

      {merchantAccount && !loading && !error && logs.length > 0 && (
        <Card>
          <div className="divide-y divide-[var(--color-border)]">
            {logs.map((log) => (
              <div key={log.id} className="flex items-start gap-4 px-5 py-3.5">
                <div className="w-32 shrink-0 text-[11px] tabular text-[var(--color-text-muted)]">
                  {new Date(log.created_at).toLocaleString("en-IN", {
                    day: "2-digit",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </div>
                <span
                  className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase"
                  style={{ color: ACTOR_COLORS[log.actor_type] ?? "var(--color-text-muted)", backgroundColor: ACTOR_BG[log.actor_type] ?? "var(--color-surface-hover)" }}
                >
                  {log.actor_type}
                </span>
                <div className="flex-1">
                  <div className="text-[13px] font-medium text-[var(--color-text-primary)]">{log.action.replace(/_/g, " ")}</div>
                  {log.reason && <div className="mt-0.5 text-xs text-[var(--color-text-secondary)]">{log.reason}</div>}
                  {log.case_id && (
                    <div className="mt-0.5 text-[11px] tabular text-[var(--color-text-muted)]">
                      case: {log.case_id.slice(0, 8)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </AppShell>
  );
}

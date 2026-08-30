import type { ReconciliationStatus } from "@/lib/types";

const STATUS_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  MATCHED: { color: "var(--color-matched)", bg: "var(--color-matched-bg)", label: "Matched" },
  EXPLAINED: { color: "var(--color-explained)", bg: "var(--color-explained-bg)", label: "Explained" },
  NEEDS_REVIEW: { color: "var(--color-review)", bg: "var(--color-review-bg)", label: "Needs Review" },
  FALSE_POSITIVE: { color: "var(--color-text-secondary)", bg: "var(--color-surface-hover)", label: "False Positive" },
  RESOLVED: { color: "var(--color-matched)", bg: "var(--color-matched-bg)", label: "Resolved" },
};

export function StatusStamp({ status }: { status: ReconciliationStatus | string }) {
  const style = STATUS_STYLES[status] ?? {
    color: "var(--color-text-secondary)",
    bg: "var(--color-surface-hover)",
    label: status,
  };
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
      style={{ color: style.color, backgroundColor: style.bg }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: style.color }} />
      {style.label}
    </span>
  );
}

export function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);

  let label = "Low confidence";
  let color = "var(--color-critical)";
  let bg = "var(--color-critical-bg)";

  if (pct >= 85) {
    label = "High confidence";
    color = "var(--color-matched)";
    bg = "var(--color-matched-bg)";
  } else if (pct >= 60) {
    label = "Medium confidence";
    color = "var(--color-review)";
    bg = "var(--color-review-bg)";
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span
          className="rounded-full px-2.5 py-1 text-[11px] font-medium"
          style={{ color, backgroundColor: bg }}
        >
          {label}
        </span>
        <span className="text-sm font-semibold tabular" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-hover)]">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

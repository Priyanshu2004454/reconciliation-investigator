export function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.8 ? "var(--color-matched)" : value >= 0.5 ? "var(--color-review)" : "var(--color-critical)";

  return (
    <div className="flex items-center gap-3">
      <div className="relative h-2 flex-1 rounded-sm bg-[var(--color-surface-hover)]">
        {[20, 40, 60, 80].map((tick) => (
          <span
            key={tick}
            className="absolute top-0 h-full w-px bg-[var(--color-bg)]"
            style={{ left: `${tick}%` }}
          />
        ))}
        <div
          className="h-full rounded-sm transition-[width]"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="font-mono text-sm tabular font-medium" style={{ color }}>
        {pct}%
      </span>
    </div>
  );
}

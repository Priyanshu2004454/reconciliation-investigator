import { ReactNode } from "react";

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-8 flex items-start justify-between">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">{title}</h1>
        {description && <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function SummaryCard({
  label,
  value,
  sublabel,
  accent,
}: {
  label: string;
  value: string;
  sublabel?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4">
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">{label}</div>
      <div
        className="mt-2 font-mono text-2xl font-semibold tabular"
        style={{ color: accent ?? "var(--color-text-primary)" }}
      >
        {value}
      </div>
      {sublabel && <div className="mt-1 text-xs text-[var(--color-text-secondary)]">{sublabel}</div>}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] ${className}`}>
      {children}
    </div>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-16 font-mono text-sm text-[var(--color-text-secondary)]">
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-sm border border-[var(--color-critical)] bg-[var(--color-critical-bg)] px-4 py-3 text-sm text-[var(--color-critical)]">
      {message}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-sm border border-dashed border-[var(--color-border)] py-16 text-center">
      <div className="text-sm font-medium text-[var(--color-text-primary)]">{title}</div>
      {description && <div className="mt-1 max-w-sm text-xs text-[var(--color-text-secondary)]">{description}</div>}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const styles = {
    primary: "bg-[var(--color-explained)] text-[#0E1013] hover:opacity-90",
    secondary:
      "border border-[var(--color-border-strong)] text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]",
    danger: "bg-[var(--color-critical)] text-[#0E1013] hover:opacity-90",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-sm px-4 py-2 text-[13px] font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-40 ${styles[variant]}`}
    >
      {children}
    </button>
  );
}

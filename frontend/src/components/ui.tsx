import { ReactNode } from "react";

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-text-primary)]">{title}</h1>
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
  icon,
}: {
  label: string;
  value: string;
  sublabel?: string;
  accent?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="card-shadow rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4 transition-shadow">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium text-[var(--color-text-muted)]">{label}</div>
        {icon && <div className="text-[var(--color-text-muted)]">{icon}</div>}
      </div>
      <div
        className="mt-2 text-[26px] font-semibold tabular leading-none"
        style={{ color: accent ?? "var(--color-text-primary)" }}
      >
        {value}
      </div>
      {sublabel && <div className="mt-1.5 text-xs text-[var(--color-text-secondary)]">{sublabel}</div>}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`card-shadow rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] transition-shadow ${className}`}>
      {children}
    </div>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-[var(--color-text-secondary)]">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--color-border-strong)] border-t-[var(--color-primary)]" />
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-[var(--color-critical-bg)] px-4 py-3 text-sm text-[var(--color-critical)]">
      {message}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] py-16 text-center">
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
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
}) {
  const styles = {
    primary: "bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] shadow-sm",
    secondary:
      "border border-[var(--color-border-strong)] bg-white text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]",
    danger: "bg-[var(--color-critical)] text-white hover:opacity-90 shadow-sm",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`rounded-lg px-4 py-2 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${styles[variant]}`}
    >
      {children}
    </button>
  );
}

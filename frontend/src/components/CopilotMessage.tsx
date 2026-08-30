import { ReactNode } from "react";

export function CopilotMessage({ role, children }: { role: "user" | "assistant"; children: ReactNode }) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-[var(--color-primary)] px-3 py-2 text-[13px] leading-snug text-white">
          {children}
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2">
      <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-ai-accent-bg)] text-[11px] text-[var(--color-ai-accent)]">
        ✦
      </div>
      <div className="max-w-[85%] space-y-2 text-[13px] leading-snug text-[var(--color-text-primary)]">
        {children}
      </div>
    </div>
  );
}

export function CopilotInsightCard({
  title,
  count,
  amount,
}: {
  title: string;
  count: number;
  amount: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2">
      <div className="text-[12.5px] font-medium text-[var(--color-text-primary)]">{title}</div>
      <div className="mt-0.5 text-[11.5px] text-[var(--color-text-secondary)]">
        {count} cases · <span className="font-medium text-[var(--color-text-primary)]">{amount}</span>
      </div>
    </div>
  );
}

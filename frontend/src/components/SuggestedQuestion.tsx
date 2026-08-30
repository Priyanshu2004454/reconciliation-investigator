export function SuggestedQuestion({ text, onClick }: { text: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded-full border border-[var(--color-border)] bg-white px-3 py-1.5 text-[12.5px] text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-ai-accent)] hover:bg-[var(--color-ai-accent-bg)] hover:text-[var(--color-ai-accent)]"
    >
      {text}
    </button>
  );
}

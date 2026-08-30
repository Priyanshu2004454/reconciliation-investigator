"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { CopilotMessage, CopilotInsightCard } from "./CopilotMessage";
import { SuggestedQuestion } from "./SuggestedQuestion";

type ChatMessage =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; insights?: { title: string; count: number; amount: string }[] };

const SUGGESTED_QUESTIONS = [
  "Why are cases still open?",
  "Show high-value exceptions",
  "What needs attention?",
  "Explain today's reconciliation",
];

// Mock response generator -- the real Copilot backend is not wired up yet.
// This exists purely so the UI/UX can be demoed and iterated on.
function mockResponse(question: string): ChatMessage {
  const q = question.toLowerCase();

  if (q.includes("attention") || q.includes("open") || q.includes("why")) {
    return {
      role: "assistant",
      text: "25 cases need review, grouped by root cause:",
      insights: [
        { title: "Missing Bank Credit", count: 12, amount: "₹12,456.78" },
        { title: "Missing Settlement", count: 6, amount: "₹4,999.00" },
        { title: "Partial Credit", count: 4, amount: "₹1,234.56" },
      ],
    };
  }
  if (q.includes("high-value") || q.includes("high value") || q.includes("exception")) {
    return {
      role: "assistant",
      text: "Exceptions with the largest financial impact:",
      insights: [
        { title: "Amount Mismatch", count: 3, amount: "₹8,940.00" },
        { title: "Missing Bank Credit", count: 2, amount: "₹6,120.50" },
      ],
    };
  }
  return {
    role: "assistant",
    text: "Today's run processed all pending records. Most gaps are timing differences that typically clear in 1-2 business days; a smaller set needs manual review.",
  };
}

function CopilotWelcome() {
  return (
    <div className="flex flex-col items-center px-4 pt-10 pb-6 text-center">
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-ai-accent-bg)] text-base text-[var(--color-ai-accent)]">
        ✦
      </div>
      <div className="text-[13px] font-semibold text-[var(--color-text-primary)]">
        Ask about your reconciliation
      </div>
      <p className="mt-1 max-w-[240px] text-[12px] leading-snug text-[var(--color-text-secondary)]">
        I can help find exceptions, explain discrepancies, and prioritize cases.
      </p>
    </div>
  );
}

export function CopilotPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const send = (text: string) => {
    if (!text.trim()) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setThinking(true);
    setTimeout(() => {
      setMessages((prev) => [...prev, mockResponse(text)]);
      setThinking(false);
    }, 700);
  };

  return (
    <>
      {open && <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />}

      {/* Mobile: bottom sheet. Desktop (sm+): right-side drawer, ~420px wide. */}
      <div
        className={`fixed inset-x-0 bottom-0 z-50 flex h-[78vh] w-full flex-col rounded-t-2xl border-t border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl transition-transform duration-200 sm:inset-x-auto sm:right-0 sm:top-0 sm:bottom-auto sm:h-full sm:w-[420px] sm:rounded-t-none sm:rounded-l-2xl sm:border-t-0 sm:border-l ${
          open ? "translate-y-0 sm:translate-x-0" : "translate-y-full sm:translate-x-full sm:translate-y-0"
        }`}
      >
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3.5">
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] text-[var(--color-ai-accent)]">✦</span>
              <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">AI Copilot</span>
              <span className="rounded-full bg-[var(--color-ai-accent-bg)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--color-ai-accent)]">
                BETA
              </span>
            </div>
            <p className="mt-0.5 text-[11.5px] text-[var(--color-text-secondary)]">
              Your reconciliation insights assistant
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {messages.length === 0 && (
            <>
              <CopilotWelcome />
              <div className="flex flex-wrap justify-center gap-1.5 px-2">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <SuggestedQuestion key={q} text={q} onClick={() => send(q)} />
                ))}
              </div>
            </>
          )}

          {messages.map((m, i) => (
            <CopilotMessage key={i} role={m.role}>
              <div>{m.text}</div>
              {m.role === "assistant" && m.insights && (
                <div className="space-y-1.5">
                  {m.insights.map((ins) => (
                    <CopilotInsightCard key={ins.title} {...ins} />
                  ))}
                  <Link
                    href="/reconciliation"
                    className="inline-block text-[12px] font-medium text-[var(--color-primary)] hover:underline"
                  >
                    View cases →
                  </Link>
                </div>
              )}
            </CopilotMessage>
          ))}

          {thinking && (
            <div className="flex items-center gap-2 pl-7 text-[12px] text-[var(--color-text-muted)]">
              <span className="inline-flex gap-0.5">
                <span className="h-1 w-1 animate-bounce rounded-full bg-[var(--color-ai-accent)] [animation-delay:-0.2s]" />
                <span className="h-1 w-1 animate-bounce rounded-full bg-[var(--color-ai-accent)] [animation-delay:-0.1s]" />
                <span className="h-1 w-1 animate-bounce rounded-full bg-[var(--color-ai-accent)]" />
              </span>
            </div>
          )}
        </div>

        <div className="border-t border-[var(--color-border)] px-3 py-2.5">
          <div className="flex items-center gap-2 rounded-xl border border-[var(--color-border-strong)] bg-white px-2.5 py-1.5">
            <button
              type="button"
              className="text-[13px] text-[var(--color-text-muted)]"
              aria-label="Voice input (not yet available)"
              title="Voice input coming soon"
            >
              🎤
            </button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send(input)}
              placeholder="Ask about your data..."
              className="flex-1 bg-transparent text-[13px] text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)]"
            />
            <button
              onClick={() => send(input)}
              disabled={!input.trim()}
              className="text-[15px] text-[var(--color-primary)] disabled:opacity-30"
              aria-label="Send"
            >
              ➤
            </button>
          </div>
          <p className="mt-1.5 text-center text-[10px] text-[var(--color-text-muted)]">
            AI can make mistakes. Verify important info.
          </p>
        </div>
      </div>
    </>
  );
}

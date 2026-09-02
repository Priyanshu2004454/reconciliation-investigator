"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { CopilotMessage, CopilotInsightCard } from "./CopilotMessage";
import { SuggestedQuestion } from "./SuggestedQuestion";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { CopilotCaseRef, CopilotInsight, CopilotSource } from "@/lib/types";

type ChatMessage =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; insights?: CopilotInsight[]; caseRefs?: CopilotCaseRef[]; sources?: CopilotSource[] }
  | { role: "error"; text: string };

const SUGGESTED_QUESTIONS = [
  "What needs attention?",
  "Show high-value exceptions",
  "Why are cases still open?",
  "Explain today's reconciliation",
];

const SOURCE_LABELS: Record<string, string> = {
  search_cases: "Case search",
  get_case: "Case detail",
  list_runs: "Run history",
  get_dashboard_summary: "Dashboard summary",
};

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 503) return "AI Copilot isn't configured on the backend yet.";
    if (err.status === 429) return "AI quota temporarily unavailable. Please try again in a moment.";
    if (err.status === 504) return "That took longer than expected. Please try again.";
    if (err.status === 502) return "Evidence could not be verified for that answer. Please rephrase your question.";
    return err.message;
  }
  return "Unable to connect. Check your connection.";
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

// ── Real browser speech recognition (Web Speech API) ────────────────────
type VoiceState = "idle" | "listening" | "unsupported";

interface SpeechRecognitionResultLike {
  [index: number]: { transcript: string };
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [index: number]: SpeechRecognitionResultLike };
}
interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

function useVoiceInput(onTranscript: (text: string) => void) {
  const [state, setState] = useState<VoiceState>("idle");
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    const w = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const SpeechRecognitionCtor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      setState("unsupported");
      return;
    }
    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-IN";

    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      onTranscript(transcript);
    };
    recognition.onerror = () => setState("idle");
    recognition.onend = () => setState((s) => (s === "listening" ? "idle" : s));

    recognitionRef.current = recognition;
    return () => recognition.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = () => {
    if (state === "unsupported" || !recognitionRef.current) return;
    if (state === "listening") {
      recognitionRef.current.stop();
      setState("idle");
    } else {
      try {
        recognitionRef.current.start();
        setState("listening");
      } catch {
        // recognition already running -- ignore
      }
    }
  };

  return { state, toggle };
}

export function CopilotPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { state: voiceState, toggle: toggleVoice } = useVoiceInput((transcript) => setInput(transcript));

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || thinking) return;
      const history = messages
        .filter((m): m is Extract<ChatMessage, { role: "user" | "assistant" }> => m.role !== "error")
        .map((m) => ({ role: m.role, text: m.text }));

      setMessages((prev) => [...prev, { role: "user", text }]);
      setInput("");
      setThinking(true);
      try {
        const res = await api.copilotChat(text, history);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: res.text, insights: res.insights, caseRefs: res.case_refs, sources: res.sources },
        ]);
      } catch (err) {
        setMessages((prev) => [...prev, { role: "error", text: friendlyError(err) }]);
      } finally {
        setThinking(false);
      }
    },
    [messages, thinking]
  );

  return (
    <>
      {open && <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />}

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

          {messages.map((m, i) => {
            if (m.role === "error") {
              return (
                <div key={i} className="rounded-lg border border-red-200 bg-[var(--color-critical-bg)] px-3 py-2 text-[12.5px] text-[var(--color-critical)]">
                  {m.text}
                </div>
              );
            }
            return (
              <CopilotMessage key={i} role={m.role}>
                <div>{m.text}</div>
                {m.role === "assistant" && m.insights && m.insights.length > 0 && (
                  <div className="space-y-1.5">
                    {m.insights.map((ins, idx) => (
                      <CopilotInsightCard key={idx} title={ins.title} count={ins.count} amount={`₹${ins.amount.toLocaleString("en-IN")}`} />
                    ))}
                  </div>
                )}
                {m.role === "assistant" && m.caseRefs && m.caseRefs.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {m.caseRefs.map((ref) => (
                      <Link
                        key={ref.case_id}
                        href={`/reconciliation/${ref.case_id}`}
                        className="rounded-full border border-[var(--color-border)] bg-white px-2.5 py-1 text-[11.5px] font-medium text-[var(--color-primary)] hover:underline"
                      >
                        {ref.label} →
                      </Link>
                    ))}
                  </div>
                )}
                {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1 pt-0.5 text-[10.5px] text-[var(--color-text-muted)]">
                    <span>Source:</span>
                    {m.sources.map((s, idx) => (
                      <span key={idx} className="rounded bg-[var(--color-bg)] px-1.5 py-0.5">
                        {SOURCE_LABELS[s.tool_name] ?? s.tool_name}
                      </span>
                    ))}
                  </div>
                )}
              </CopilotMessage>
            );
          })}

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
          {voiceState === "unsupported" && (
            <p className="mb-1.5 text-center text-[10px] text-[var(--color-text-muted)]">
              Voice input isn&apos;t supported in this browser.
            </p>
          )}
          <div
            className={`flex items-center gap-2 rounded-xl border bg-white px-2.5 py-1.5 ${
              voiceState === "listening" ? "border-[var(--color-ai-accent)]" : "border-[var(--color-border-strong)]"
            }`}
          >
            <button
              type="button"
              onClick={toggleVoice}
              disabled={voiceState === "unsupported"}
              className={`text-[13px] ${voiceState === "listening" ? "text-[var(--color-ai-accent)]" : "text-[var(--color-text-muted)]"} disabled:opacity-30`}
              aria-label={voiceState === "listening" ? "Stop listening" : "Start voice input"}
              title={voiceState === "unsupported" ? "Voice input isn't supported in this browser" : "Voice input"}
            >
              🎙
            </button>
            {voiceState === "listening" ? (
              <span className="flex flex-1 items-center gap-1.5 text-[13px] text-[var(--color-ai-accent)]">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-ai-accent)]" />
                Listening… {input}
              </span>
            ) : (
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send(input)}
                placeholder="Ask about your data..."
                className="flex-1 bg-transparent text-[13px] text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)]"
              />
            )}
            <button
              onClick={() => send(input)}
              disabled={!input.trim() || thinking}
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

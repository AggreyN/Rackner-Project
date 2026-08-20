"use client";

// Per-opportunity AI assistant. Answers come from the gov-safe LLM with
// citations back to the source document — clicking a citation jumps the
// source pane, same grounding rule as everywhere else.
//
// Controlled: conversation state lives in useChat() on the page, so the
// inline panel and the floating Anvil window share one transcript.

import { useState } from "react";
import type { ChatState } from "@/hooks/useChat";
import type { CiteTarget } from "./ObligationsPanel";

export default function ChatPanel({
  chat,
  onCite,
  frameless = false,
  autoFocus = false,
}: {
  chat: ChatState;
  onCite: (target: CiteTarget) => void;
  /** Floating-window mode: no card border, fills its container. */
  frameless?: boolean;
  autoFocus?: boolean;
}) {
  const { messages, busy, send } = chat;
  const [input, setInput] = useState("");

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const q = input.trim();
    if (!q || busy) return;
    setInput("");
    // The send logic (history snapshot, error-bubble filtering, blank-answer
    // guard) moved into useChat so the inline panel and the floating window
    // share one transcript.
    await send(q);
  }

  return (
    <div
      className={
        frameless
          ? "flex h-full min-h-0 flex-col p-3"
          : "border border-[#d7dee6] bg-white p-4 sm:p-5"
      }
      data-testid="chat-panel"
    >
      {!frameless && (
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
          Anvil AI — Ask about this opportunity
        </h3>
      )}

      <div className={"space-y-2 " + (frameless ? "min-h-0 flex-1 overflow-y-auto" : "")}>
        {messages.length === 0 && (
          <p className="text-xs text-[#51606f]">
            Try: “What would disqualify us from bidding?” or “When is it due?”
          </p>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div
              key={i}
              className="ml-10 rounded-lg border border-[#16324f] bg-[#16324f] px-3 py-2 text-[12.5px] text-white"
            >
              {m.text}
            </div>
          ) : (
            <div
              key={i}
              className="rounded-lg border border-[#d7dee6] bg-[#f5f7f9] px-3 py-2 text-[12.5px] text-[#1f2933]"
            >
              {m.text}
              {m.citations && m.citations.length > 0 && (
                <span className="mt-1 block text-[#51606f]">
                  — cited to{" "}
                  {m.citations.map((c, j) => (
                    <button
                      key={`${c.section}-${j}`}
                      // Verified quotes ride the same highlight path as
                      // obligations; unverified ones still jump to the
                      // section but highlight nothing (nothing is grounded).
                      onClick={() =>
                        onCite({
                          section: c.section,
                          quote: c.verified ? c.verbatim_quote : undefined,
                        })
                      }
                      title={
                        c.verified
                          ? undefined
                          : "Quote could not be verified against the source"
                      }
                      className="text-[#16324f] underline underline-offset-2 hover:text-[#0f2438]"
                    >
                      {c.section}
                      {j < m.citations!.length - 1 ? ", " : ""}
                    </button>
                  ))}
                </span>
              )}
            </div>
          )
        )}
        {busy && <p className="text-xs text-[#51606f]">Anvil is reading the document…</p>}
      </div>

      <form onSubmit={submit} className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoFocus={autoFocus}
          placeholder="Ask Anvil Anything about this contract…"
          className="w-full flex-1 rounded-md border border-[#d7dee6] px-3 py-2 text-sm focus:border-[#16324f] focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-md bg-[#16324f] px-3.5 py-2 text-sm font-semibold text-white hover:bg-[#0f2438] disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}

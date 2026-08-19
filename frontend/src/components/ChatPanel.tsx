"use client";

// Per-opportunity AI assistant. Answers come from the gov-safe LLM with
// citations back to the source document — clicking a citation jumps the
// source pane, same grounding rule as everywhere else.

import { useState } from "react";
import { askChat } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import type { CiteTarget } from "./ObligationsPanel";

export default function ChatPanel({
  opportunityId,
  onCite,
}: {
  opportunityId: string;
  onCite: (target: CiteTarget) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    // Snapshot the transcript BEFORE appending this question — these are the
    // prior turns the backend uses to resolve follow-ups.
    // Synthetic error bubbles are UI chrome, not conversation — sending
    // them as assistant turns taught the model to apologize for outages.
    const history = messages.filter((m) => !m.error);
    setMessages((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const res = await askChat(opportunityId, question, history);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          // Belt-and-suspenders: the backend never sends blank answers anymore,
          // but a blank bubble must be impossible at this layer too.
          text: res.answer?.trim()
            ? res.answer
            : "Anvil had trouble with that one — try asking again.",
          citations: res.citations,
        },
      ]);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "Couldn't reach Anvil — try again.", error: true },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border border-[#d7dee6] bg-white p-4 sm:p-5" data-testid="chat-panel">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
        Anvil AI — Ask about this opportunity
      </h3>

      <div className="space-y-2">
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

      <form onSubmit={send} className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
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

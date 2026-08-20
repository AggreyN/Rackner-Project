"use client";

// One conversation per opportunity, shared by every chat surface.
// The inline panel and the floating window both render from this state, so
// a question asked in one shows up in the other — two views, one transcript.

import { useCallback, useState } from "react";
import { askChat } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

export interface ChatState {
  messages: ChatMessage[];
  busy: boolean;
  send: (question: string) => Promise<void>;
}

export function useChat(opportunityId: string): ChatState {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy) return;
      // Snapshot the transcript BEFORE appending this question — these are
      // the prior turns the backend uses to resolve follow-ups.
      const history = messages;
      setMessages((m) => [...m, { role: "user", text: q }]);
      setBusy(true);
      try {
        const res = await askChat(opportunityId, q, history);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            // Belt-and-suspenders: a blank bubble must be impossible here
            // even if the backend misbehaves.
            text: res.answer?.trim()
              ? res.answer
              : "Anvil had trouble with that one — try asking again.",
            citations: res.citations,
          },
        ]);
      } catch {
        setMessages((m) => [
          ...m,
          { role: "assistant", text: "Couldn't reach Anvil — try again." },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [opportunityId, busy, messages]
  );

  return { messages, busy, send };
}

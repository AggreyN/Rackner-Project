"use client";

// One obligation: plain English up top, evidence underneath.
// Clicking "View in document" tells the workspace to jump the PDF pane
// to the cited page — the grounding moment.

import type { Obligation } from "@/lib/types";
import { updateObligationStatus } from "@/lib/api";
import { useState } from "react";

interface Props {
  obligation: Obligation;
  onCite: (page: number | null) => void;
}

export default function ObligationCard({ obligation: o, onCite }: Props) {
  const [status, setStatus] = useState(o.status);
  const dim = !o.relevant_to_role;

  async function cycleStatus() {
    const next = status === "open" ? "in-review" : status === "in-review" ? "done" : "open";
    setStatus(next); // optimistic
    try {
      await updateObligationStatus(o.id, next);
    } catch {
      setStatus(status); // roll back on failure
    }
  }

  return (
    <div
      className={
        "border border-[#d7dee6] bg-white p-4 " + (dim ? "opacity-55" : "")
      }
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm leading-relaxed text-[#16324f]">{o.plain_english_text}</p>
        <button
          onClick={cycleStatus}
          title="Click to cycle open → in-review → done"
          className={
            "shrink-0 border px-2 py-0.5 text-xs " +
            (status === "done"
              ? "border-[#1e7a46] text-[#1e7a46]"
              : status === "in-review"
              ? "border-[#9a6a1e] text-[#9a6a1e]"
              : "border-[#d7dee6] text-[#51606f]")
          }
        >
          {status}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#51606f]">
        {o.trigger_or_deadline && <span>⏱ {o.trigger_or_deadline}</span>}
        {o.responsible_party && <span>{o.responsible_party}</span>}
        {o.obligation_type && <span className="uppercase tracking-wide">{o.obligation_type}</span>}
        {o.confidence != null && <span>{Math.round(o.confidence * 100)}% confidence</span>}
        <span className={o.verified ? "text-[#1e7a46]" : "text-[#9a6a1e]"}>
          {o.verified ? "✓ quote verified in source" : "⚠ quote not verified"}
        </span>
      </div>

      {o.verbatim_quote && (
        <blockquote className="mt-3 border-l-2 border-[#16324f] bg-[#f5f7f9] px-3 py-2 text-xs italic text-[#51606f]">
          “{o.verbatim_quote}”
        </blockquote>
      )}

      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-[#51606f]">
          {o.roles.length > 0 && <>Relevant to: {o.roles.join(", ")}</>}
        </span>
        {o.page != null && (
          <button
            onClick={() => onCite(o.page)}
            className="text-xs font-medium text-[#16324f] underline underline-offset-2 hover:text-[#0f2438]"
          >
            View in document → p.{o.page}
          </button>
        )}
      </div>
    </div>
  );
}

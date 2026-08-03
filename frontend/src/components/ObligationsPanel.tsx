"use client";

// Key obligations & requirements, grouped by time (kept from the original
// product) or by type. Each carries its verbatim quote + citation; clicking
// the quote jumps the source pane to the cited section — the grounding
// moment. Unverified quotes are flagged, never hidden (anti-hallucination).

import { useState } from "react";
import type { Obligation } from "@/lib/types";
import { TIME_BUCKET_LABELS, TIME_BUCKET_ORDER } from "@/lib/types";

export interface CiteTarget {
  section: string;
  quote?: string;
}

export default function ObligationsPanel({
  obligations,
  onCite,
}: {
  obligations: Obligation[];
  onCite: (target: CiteTarget) => void;
}) {
  const [groupBy, setGroupBy] = useState<"time" | "type">("time");

  const groups =
    groupBy === "time"
      ? TIME_BUCKET_ORDER.map((bucket) => ({
          label: TIME_BUCKET_LABELS[bucket],
          items: obligations.filter((o) => o.time_bucket === bucket),
        })).filter((g) => g.items.length > 0)
      : [...new Set(obligations.map((o) => o.obligation_type))].map((t) => ({
          label: t.charAt(0).toUpperCase() + t.slice(1),
          items: obligations.filter((o) => o.obligation_type === t),
        }));

  return (
    <div className="border border-[#d7dee6] bg-white p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-[#51606f]">
          Key obligations &amp; requirements
        </h3>
        <div className="flex gap-1.5">
          {(["time", "type"] as const).map((g) => (
            <button
              key={g}
              onClick={() => setGroupBy(g)}
              className={
                "rounded-full border px-2.5 py-1 text-[11.5px] " +
                (groupBy === g
                  ? "border-[#16324f] bg-[#16324f] text-white"
                  : "border-[#d7dee6] bg-white text-[#16324f] hover:border-[#16324f]")
              }
            >
              By {g}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        {groups.map((g) => (
          <section key={g.label}>
            <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#51606f]">
              {g.label} <span className="font-normal normal-case">({g.items.length})</span>
            </h4>
            <div className="space-y-2.5">
              {g.items.map((o) => (
                <ObligationRow key={o.id} obligation={o} onCite={onCite} />
              ))}
            </div>
          </section>
        ))}
        {obligations.length === 0 && (
          <p className="text-sm text-[#51606f]">No obligations extracted.</p>
        )}
      </div>
    </div>
  );
}

function ObligationRow({
  obligation: o,
  onCite,
}: {
  obligation: Obligation;
  onCite: (target: CiteTarget) => void;
}) {
  return (
    <div className="rounded-md border border-[#d7dee6] p-3" data-testid="obligation">
      <div className="flex items-start justify-between gap-2.5">
        <span className="text-[13.5px] font-semibold leading-snug text-[#16324f]">{o.text}</span>
        <span className="shrink-0 whitespace-nowrap rounded bg-[#16324f] px-1.5 py-0.5 text-[10.5px] text-white">
          {o.deadline_label}
        </span>
      </div>
      <button
        onClick={() => onCite({ section: o.citation.section, quote: o.verbatim_quote })}
        className="mt-2 block w-full border-l-2 border-[#16324f] bg-[#f5f7f9] px-2.5 py-1.5 text-left text-[11.5px] italic text-[#51606f] hover:text-[#16324f]"
        title="View in the source document"
      >
        “{o.verbatim_quote}” — {o.citation.section}
        {o.citation.page !== null && `, p.${o.citation.page}`}
      </button>
      <span
        className={
          "mt-1.5 inline-block text-[10.5px] " +
          (o.verified ? "text-[#1e7a46]" : "text-[#9a6a1e]")
        }
      >
        {o.verified ? "✓ quote verified in source" : "⚠ quote not verified — treat with caution"}
      </span>
    </div>
  );
}

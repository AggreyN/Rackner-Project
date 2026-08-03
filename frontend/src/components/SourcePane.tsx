"use client";

// The right pane: the parsed source document, collapsible (Claude-style
// dual view — analysis left, evidence right). Citation clicks scroll the
// cited section into view and set the quote glowing. The backend contract
// guarantees verbatim quotes are exact substrings of section text, so
// highlighting is a plain string match — no fuzzy logic to go wrong.

import { useEffect, useRef } from "react";
import type { SourceDocument } from "@/lib/types";
import type { CiteTarget } from "./ObligationsPanel";

interface Props {
  doc: SourceDocument | null;
  /** True when no solicitation exists yet (expiring award / recompete). */
  unavailable?: boolean;
  cite: CiteTarget | null;
  collapsed: boolean;
  onToggle: () => void;
}

/** "§L.2" → "L.2" so citations match section refs. */
function normalizeRef(section: string): string {
  return section.replace(/^§/, "").trim();
}

export default function SourcePane({ doc, unavailable, cite, collapsed, onToggle }: Props) {
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    if (!cite || collapsed) return;
    const el = sectionRefs.current[normalizeRef(cite.section)];
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [cite, collapsed]);

  if (collapsed) {
    return (
      <button
        onClick={onToggle}
        title="Show source document"
        data-testid="source-expand"
        className="hidden h-full w-10 shrink-0 items-center justify-center border-l border-[#d7dee6] bg-white text-[#16324f] hover:bg-[#f5f7f9] lg:flex"
      >
        <span className="rotate-180 text-[11px] uppercase tracking-widest [writing-mode:vertical-rl]">
          Source document
        </span>
      </button>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-white lg:border-l lg:border-[#d7dee6]">
      <div className="flex items-center justify-between border-b border-[#d7dee6] px-4 py-2.5">
        <span className="truncate text-[11px] font-semibold uppercase tracking-widest text-[#51606f]">
          {doc?.label ?? "Source document"}
        </span>
        <button
          onClick={onToggle}
          data-testid="source-collapse"
          className="hidden text-xs text-[#16324f] underline underline-offset-2 hover:text-[#0f2438] lg:block"
        >
          Collapse
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 text-[12.5px] leading-relaxed text-[#333]">
        {unavailable ? (
          <div data-testid="source-unavailable" className="text-[#51606f]">
            <p className="font-semibold text-[#16324f]">No solicitation posted yet</p>
            <p className="mt-1.5 leading-relaxed">
              This is an existing award nearing the end of its period of performance, tracked from
              USAspending.gov. There is no RFP to read or cite until the recompete is solicited.
            </p>
            <p className="mt-3 leading-relaxed">
              That is the advantage: the requirement can still be shaped. Use the spend history and
              contact on the left to start capture now.
            </p>
          </div>
        ) : !doc ? (
          <p className="text-[#51606f]">Loading the source document…</p>
        ) : (
          doc.sections.map((s) => {
            const active = cite && normalizeRef(cite.section) === s.ref;
            return (
              <div
                key={s.ref}
                ref={(el) => {
                  sectionRefs.current[s.ref] = el;
                }}
                className="scroll-mt-3"
              >
                <h5 className="mb-1.5 mt-4 text-[13px] font-semibold text-[#16324f] first:mt-0">
                  {s.heading}
                  <span className="ml-2 font-normal text-[#51606f]">p.{s.page}</span>
                </h5>
                <p>
                  <SectionText text={s.text} quote={active ? cite?.quote : undefined} />
                </p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function SectionText({ text, quote }: { text: string; quote?: string }) {
  if (!quote) return <>{text}</>;
  const idx = text.indexOf(quote);
  if (idx === -1) return <>{text}</>; // unverified quote — nothing to ground
  return (
    <>
      {text.slice(0, idx)}
      <mark
        data-testid="cite-highlight"
        className="border-b-2 border-[#f0c419] bg-[#fff3bf] px-0"
      >
        {quote}
      </mark>
      {text.slice(idx + quote.length)}
    </>
  );
}

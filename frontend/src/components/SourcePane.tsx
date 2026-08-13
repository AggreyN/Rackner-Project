"use client";

// The right pane: the parsed source document, collapsible (Claude-style
// dual view — analysis left, evidence right). Citation clicks scroll the
// cited section into view and set the quote glowing. The backend contract
// guarantees verbatim quotes are exact substrings of section text, so
// highlighting is a plain string match — no fuzzy logic to go wrong.
//
// Big-package mode: full solicitation packages now arrive with 100+
// sections (~200K chars). Above LARGE_DOC_SECTIONS the pane switches to a
// jump-list TOC + collapsed-by-default sections, so only opened section
// bodies are in the DOM — scrolling stays smooth on a projector laptop.
// Small documents render fully expanded, exactly as before.

import { useEffect, useRef, useState } from "react";
import type { SourceDocument } from "@/lib/types";
import type { CiteTarget } from "./ObligationsPanel";

const LARGE_DOC_SECTIONS = 20;

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
  const isLarge = (doc?.sections.length ?? 0) > LARGE_DOC_SECTIONS;

  // Which sections are open (large docs only — small docs are always open).
  const [openRefs, setOpenRefs] = useState<Set<string>>(new Set());

  // Render-phase adjustment (the React-sanctioned pattern): when a new cite
  // arrives, force its section open BEFORE the commit, so the scroll effect
  // below finds the body already in the DOM.
  const [prevCite, setPrevCite] = useState<CiteTarget | null>(null);
  if (cite !== prevCite) {
    setPrevCite(cite);
    if (cite) {
      const r = normalizeRef(cite.section);
      if (!openRefs.has(r)) setOpenRefs(new Set(openRefs).add(r));
    }
  }

  useEffect(() => {
    if (!cite || collapsed) return;
    const el = sectionRefs.current[normalizeRef(cite.section)];
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [cite, collapsed]);

  function toggleSection(ref: string) {
    setOpenRefs((prev) => {
      const next = new Set(prev);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });
  }

  function jumpTo(ref: string) {
    setOpenRefs((prev) => (prev.has(ref) ? prev : new Set(prev).add(ref)));
    sectionRefs.current[ref]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

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

  const allOpen = doc ? openRefs.size >= doc.sections.length : false;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-white lg:border-l lg:border-[#d7dee6]">
      <div className="flex items-center justify-between gap-3 border-b border-[#d7dee6] px-4 py-2.5">
        <span className="truncate text-[11px] font-semibold uppercase tracking-widest text-[#51606f]">
          {doc?.label ?? "Source document"}
          {isLarge && doc && (
            <span className="ml-2 font-normal normal-case tracking-normal">
              · {doc.sections.length} sections
            </span>
          )}
        </span>
        <div className="flex shrink-0 items-center gap-3">
          {isLarge && (
            <button
              onClick={() =>
                setOpenRefs(allOpen ? new Set() : new Set(doc!.sections.map((s) => s.ref)))
              }
              data-testid="toggle-all-sections"
              className="text-xs text-[#16324f] underline underline-offset-2 hover:text-[#0f2438]"
            >
              {allOpen ? "Collapse all" : "Expand all"}
            </button>
          )}
          <button
            onClick={onToggle}
            data-testid="source-collapse"
            className="hidden text-xs text-[#16324f] underline underline-offset-2 hover:text-[#0f2438] lg:block"
          >
            Collapse
          </button>
        </div>
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
          <>
            {isLarge && (
              <nav
                data-testid="source-toc"
                aria-label="Document sections"
                className="mb-4 rounded-md border border-[#d7dee6] bg-[#f5f7f9] p-2.5"
              >
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-[#51606f]">
                  Jump to section
                </div>
                <div className="flex max-h-28 flex-wrap gap-1 overflow-y-auto">
                  {doc.sections.map((s) => (
                    <button
                      key={s.ref}
                      onClick={() => jumpTo(s.ref)}
                      title={s.heading}
                      data-testid="toc-entry"
                      className="rounded border border-[#d7dee6] bg-white px-1.5 py-0.5 text-[10.5px] text-[#16324f] hover:border-[#16324f]"
                    >
                      {s.ref}
                    </button>
                  ))}
                </div>
              </nav>
            )}

            {doc.sections.map((s) => {
              const active = cite && normalizeRef(cite.section) === s.ref;
              const open = !isLarge || openRefs.has(s.ref);
              return (
                <div
                  key={s.ref}
                  ref={(el) => {
                    sectionRefs.current[s.ref] = el;
                  }}
                  className="scroll-mt-3"
                >
                  {isLarge ? (
                    <button
                      onClick={() => toggleSection(s.ref)}
                      aria-expanded={open}
                      data-testid="section-toggle"
                      className="mt-2 flex w-full items-baseline gap-2 border-b border-[#f5f7f9] py-1 text-left first:mt-0 hover:bg-[#f5f7f9]"
                    >
                      <span className="text-[#51606f]">{open ? "▾" : "▸"}</span>
                      <span className="text-[13px] font-semibold text-[#16324f]">{s.heading}</span>
                      <span className="ml-auto shrink-0 text-[11px] font-normal text-[#51606f]">
                        p.{s.page}
                      </span>
                    </button>
                  ) : (
                    <h5 className="mb-1.5 mt-4 text-[13px] font-semibold text-[#16324f] first:mt-0">
                      {s.heading}
                      <span className="ml-2 font-normal text-[#51606f]">p.{s.page}</span>
                    </h5>
                  )}
                  {open && (
                    <p data-testid="section-body" className={isLarge ? "py-1.5" : undefined}>
                      <SectionText text={s.text} quote={active ? cite?.quote : undefined} />
                    </p>
                  )}
                </div>
              );
            })}
          </>
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

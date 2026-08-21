"use client";

// The right pane: the parsed source document, collapsible (Claude-style
// dual view — analysis left, evidence right). Citation clicks scroll the
// cited section into view and set the quote glowing. The backend contract
// guarantees verbatim quotes are exact substrings of section text, so
// highlighting is a plain string match — no fuzzy logic to go wrong.
//
// SCALE NOTES — matched to app/services/ingest.py::split_sections:
//   · Sections are heading-to-heading slices of the whole document, so their
//     size is UNBOUNDED. A package with few headings yields a handful of
//     enormous sections; one with many yields a hundred small ones. Both
//     shapes have to stay smooth, so large-mode triggers on section count
//     OR total characters — never count alone.
//   · Refs come deduped ("52.212-4 #2") and may be clause ids, section
//     letters, dotted paras, "p88" page fallbacks, or "0" for the preamble.
//     They can contain spaces and '#', so they are display-truncated.
//   · Long bodies render clamped with a "show full section" affordance, so
//     opening any single section costs a bounded amount of layout. The cited
//     section always renders in full — the highlight must never be clipped.

import { useEffect, useRef, useState } from "react";
import type { SourceDocument } from "@/lib/types";
import type { CiteTarget } from "./ObligationsPanel";

/** Either dimension flips the pane into large-document mode. */
const LARGE_DOC_SECTIONS = 20;
const LARGE_DOC_CHARS = 40_000;
/** Bodies longer than this render clamped until asked for in full. */
const CLAMP_CHARS = 4_000;

interface Props {
  doc: SourceDocument | null;
  /** True when no solicitation exists yet (expiring award / recompete). */
  unavailable?: boolean;
  cite: CiteTarget | null;
  collapsed: boolean;
  onToggle: () => void;
}

/** "§L.2" → "L.2". Backend stores refs without the sign (SCHEMA_v2) but
 *  citations may still carry it; the dedupe suffix ("#2") is significant
 *  and must survive. */
function normalizeRef(section: string): string {
  return section.replace(/^§/, "").trim();
}

export default function SourcePane({ doc, unavailable, cite, collapsed, onToggle }: Props) {
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const sections = doc?.sections ?? [];
  const totalChars = sections.reduce((n, s) => n + s.text.length, 0);
  const isLarge = sections.length > LARGE_DOC_SECTIONS || totalChars > LARGE_DOC_CHARS;

  // Attachment transparency: a quota-starved document must SAY it is partial.
  // pending = links not yet resolved (they load on a later visit once SAM.gov
  // quota allows); unreadable = resolved links that yielded no text (scanned
  // images, dead files) — those will never add sections.
  const expected = doc?.attachments_expected ?? 0;
  const accounted = doc?.attachments_accounted ?? 0;
  const ingested = doc?.attachments_ingested ?? 0;
  const pendingAttachments = Math.max(0, expected - accounted);
  const unreadableAttachments =
    pendingAttachments === 0 ? Math.max(0, expected - ingested) : 0;

  // Which sections are open (large docs only) and which long bodies are
  // showing their full text.
  const [openRefs, setOpenRefs] = useState<Set<string>>(new Set());
  const [fullRefs, setFullRefs] = useState<Set<string>>(new Set());

  // Render-phase adjustment: when a new cite arrives, force its section open
  // AND unclamped before the commit, so the scroll effect finds the body in
  // the DOM and the quote is never outside the rendered slice.
  const [prevCite, setPrevCite] = useState<CiteTarget | null>(null);
  if (cite !== prevCite) {
    setPrevCite(cite);
    if (cite) {
      const r = normalizeRef(cite.section);
      if (!openRefs.has(r)) setOpenRefs(new Set(openRefs).add(r));
      if (!fullRefs.has(r)) setFullRefs(new Set(fullRefs).add(r));
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

  const allOpen = sections.length > 0 && openRefs.size >= sections.length;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-white lg:border-l lg:border-[#d7dee6]">
      <div className="flex items-center justify-between gap-3 border-b border-[#d7dee6] px-4 py-2.5">
        <span className="truncate text-[11px] font-semibold uppercase tracking-widest text-[#51606f]">
          {doc?.label ?? "Source document"}
          {isLarge && (
            <span className="ml-2 font-normal normal-case tracking-normal">
              · {sections.length} sections · {Math.round(totalChars / 1000)}K chars
            </span>
          )}
        </span>
        <div className="flex shrink-0 items-center gap-3">
          {isLarge && (
            <button
              onClick={() =>
                setOpenRefs(allOpen ? new Set() : new Set(sections.map((s) => s.ref)))
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
            {pendingAttachments > 0 && (
              <div
                data-testid="attachments-pending"
                className="mb-4 rounded-md border border-[#e6dcbd] bg-[#fdf9ee] px-3.5 py-2.5 text-xs leading-relaxed text-[#6b5a1c]"
              >
                <span className="font-semibold">
                  {ingested} of {expected} contract attachments loaded.
                </span>{" "}
                SAM.gov&apos;s daily API quota stopped the rest — they load automatically on a
                later visit. Citations and page numbers cover only what&apos;s shown here.
              </div>
            )}
            {unreadableAttachments > 0 && (
              <div
                data-testid="attachments-unreadable"
                className="mb-4 rounded-md border border-[#d7dee6] bg-[#f5f7f9] px-3.5 py-2.5 text-xs leading-relaxed text-[#51606f]"
              >
                {unreadableAttachments} of {expected} attachment
                {expected === 1 ? "" : "s"} on this notice had no readable text (scanned image
                or dead link) and cannot be shown or cited.
              </div>
            )}
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
                  {sections.map((s) => (
                    <button
                      key={s.ref}
                      onClick={() => jumpTo(s.ref)}
                      title={`${s.ref}${s.heading ? ` — ${s.heading}` : ""}`}
                      data-testid="toc-entry"
                      // Refs can be long ("52.212-4 #2") — clamp the chip so a
                      // wide ref can't blow out the TOC grid.
                      className="max-w-[7.5rem] truncate rounded border border-[#d7dee6] bg-white px-1.5 py-0.5 text-[10.5px] text-[#16324f] hover:border-[#16324f]"
                    >
                      {s.ref}
                    </button>
                  ))}
                </div>
              </nav>
            )}

            {sections.map((s) => {
              const active = cite !== null && normalizeRef(cite.section) === s.ref;
              const open = !isLarge || openRefs.has(s.ref);
              const showFull = fullRefs.has(s.ref) || active;
              const clamped = s.text.length > CLAMP_CHARS && !showFull;
              const body = clamped ? s.text.slice(0, CLAMP_CHARS) : s.text;
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
                      <span className="min-w-0 truncate text-[13px] font-semibold text-[#16324f]">
                        {s.heading || s.ref}
                      </span>
                      <span className="ml-auto shrink-0 text-[11px] font-normal text-[#51606f]">
                        p.{s.page}
                      </span>
                    </button>
                  ) : (
                    <h5 className="mb-1.5 mt-4 text-[13px] font-semibold text-[#16324f] first:mt-0">
                      {s.heading || s.ref}
                      <span className="ml-2 font-normal text-[#51606f]">p.{s.page}</span>
                    </h5>
                  )}
                  {open && (
                    <>
                      <p data-testid="section-body" className={isLarge ? "py-1.5" : undefined}>
                        <SectionText text={body} quote={active ? cite?.quote : undefined} />
                        {clamped && "…"}
                      </p>
                      {clamped && (
                        <button
                          onClick={() => setFullRefs((prev) => new Set(prev).add(s.ref))}
                          data-testid="show-full-section"
                          className="mb-1 text-[11px] text-[#16324f] underline underline-offset-2 hover:text-[#0f2438]"
                        >
                          Show full section ({Math.round(s.text.length / 1000)}K characters)
                        </button>
                      )}
                    </>
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

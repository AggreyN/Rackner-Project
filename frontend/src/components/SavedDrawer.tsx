"use client";

// The saved-opportunities dashboard: a slim tab pinned to the right edge of
// every signed-in page. Click it and a drawer slides out with the user's
// bookmarks — title, agency, fit, and a one-click path back into the
// analysis. Saves live per user (see lib/bookmarks.ts).

import { useEffect, useState } from "react";
import Link from "next/link";
import { getOpportunity } from "@/lib/api";
import { hydrateBookmarks, useBookmarks } from "@/lib/bookmarks";
import type { OpportunitySummary } from "@/lib/types";
import BookmarkStar from "./BookmarkStar";
import ScoreBadge from "./ScoreBadge";

export default function SavedDrawer() {
  const ids = useBookmarks();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<OpportunitySummary[] | null>(null);

  // This tab is on every signed-in screen, so it is where the server's saved
  // list gets pulled in — otherwise stars saved on another device (or by an
  // admin) would never appear here.
  useEffect(() => {
    void hydrateBookmarks();
  }, []);

  // Resolve ids → summaries whenever the drawer is open. Unresolvable ids
  // (e.g. an imported doc cleared by a mock reset) are dropped, not fatal.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    Promise.all(ids.map((id) => getOpportunity(id).catch(() => null))).then((res) => {
      if (!cancelled) setItems(res.filter((o): o is OpportunitySummary => o !== null));
    });
    return () => {
      cancelled = true;
    };
  }, [open, ids]);

  return (
    <>
      {/* edge tab — always visible, shows the count */}
      <button
        onClick={() => setOpen(true)}
        data-testid="saved-tab"
        aria-label={`Open saved opportunities (${ids.length})`}
        // top-28, not centered: the collapsed source pane is a full-height
        // rail on this same edge, and its click target is the vertical
        // center — the tab must sit clear of it.
        className="fixed right-0 top-28 z-30 rounded-l-md border border-r-0 border-[#d7dee6] bg-[#16324f] px-1.5 py-3 text-white shadow-sm hover:bg-[#0f2438]"
      >
        <span className="block text-sm leading-none">★</span>
        <span className="mt-1 block text-[10px] font-semibold leading-none">{ids.length}</span>
        <span className="mt-1.5 block rotate-180 text-[9px] uppercase tracking-widest [writing-mode:vertical-rl]">
          Saved
        </span>
      </button>

      {open && (
        <div className="fixed inset-0 z-40" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-[#16324f]/30" />
          <aside
            data-testid="saved-drawer"
            role="dialog"
            aria-label="Saved opportunities"
            onClick={(e) => e.stopPropagation()}
            className="absolute bottom-0 right-0 top-0 flex w-full max-w-sm flex-col border-l border-[#d7dee6] bg-white shadow-[-8px_0_30px_rgba(22,50,79,.15)]"
          >
            <div className="flex items-center justify-between border-b border-[#d7dee6] px-4 py-3">
              <h2 className="text-sm font-semibold text-[#16324f]">
                Saved opportunities <span className="text-[#51606f]">({ids.length})</span>
              </h2>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close saved drawer"
                data-testid="saved-drawer-close"
                className="rounded px-1.5 text-[#51606f] hover:bg-[#f5f7f9] hover:text-[#16324f]"
              >
                ✕
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {ids.length === 0 ? (
                <p className="p-3 text-sm leading-relaxed text-[#51606f]">
                  Nothing saved yet. Click the ☆ on any opportunity to keep it here — saves are
                  per account.
                </p>
              ) : items === null ? (
                <div className="space-y-2" aria-hidden>
                  {ids.map((id) => (
                    <div key={id} className="h-16 animate-pulse rounded border border-[#d7dee6]" />
                  ))}
                </div>
              ) : (
                <div className="space-y-2">
                  {items.map((o) => (
                    <Link
                      key={o.id}
                      href={`/opportunity/${o.id}`}
                      onClick={() => setOpen(false)}
                      data-testid="saved-item"
                      className="flex items-center gap-3 rounded border border-[#d7dee6] p-3 hover:border-[#16324f]"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-semibold text-[#16324f]">
                          {o.title}
                        </div>
                        <div className="truncate text-[11px] text-[#51606f]">
                          {[o.agency, o.office].filter(Boolean).join(" · ")}
                        </div>
                      </div>
                      <ScoreBadge score={o.fit_score} />
                      <BookmarkStar id={o.id} />
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

"use client";

// The right pane: the source document, collapsible (Claude-style dual view).
// Week 7: react-pdf with span-level highlight — click an obligation and the
// exact cited sentence glows. If pdf.js can't load (odd browser, worker
// blocked), we degrade to the v1 iframe viewer so the demo never dies.

import dynamic from "next/dynamic";
import { useState } from "react";
import type { CiteTarget } from "@/lib/types";

const PdfViewer = dynamic(() => import("./PdfViewer"), {
  ssr: false,
  loading: () => (
    <p className="p-6 text-sm text-[#51606f]" role="status">
      Loading the document viewer…
    </p>
  ),
});

interface Props {
  pdfUrl: string;
  cite: CiteTarget | null;   // set by "View in document" clicks
  collapsed: boolean;
  onToggle: () => void;
}

export default function DocumentPane({ pdfUrl, cite, collapsed, onToggle }: Props) {
  const [fallback, setFallback] = useState(false);

  if (collapsed) {
    return (
      <button
        onClick={onToggle}
        title="Show document"
        className="flex h-full w-full items-center justify-center border-l border-[#d7dee6] bg-white text-[#16324f] hover:bg-[#f5f7f9]"
      >
        <span className="rotate-180 text-xs tracking-widest [writing-mode:vertical-rl]">
          SHOW DOCUMENT
        </span>
      </button>
    );
  }

  const iframeSrc = cite?.page ? `${pdfUrl}#page=${cite.page}` : pdfUrl;

  return (
    <div className="flex h-full w-full flex-col border-[#d7dee6] bg-white lg:border-l">
      <div className="flex items-center justify-between border-b border-[#d7dee6] px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-[#51606f]">
          Source document {cite?.page ? `· p.${cite.page}` : ""}
        </span>
        <button
          onClick={onToggle}
          className="hidden text-xs text-[#16324f] underline underline-offset-2 hover:text-[#0f2438] lg:block"
        >
          Collapse
        </button>
      </div>
      {fallback ? (
        // key forces the iframe to honor page jumps on re-cite
        <iframe key={iframeSrc} src={iframeSrc} title="Source document" className="h-full w-full" />
      ) : (
        <PdfViewer pdfUrl={pdfUrl} cite={cite} onError={() => setFallback(true)} />
      )}
    </div>
  );
}

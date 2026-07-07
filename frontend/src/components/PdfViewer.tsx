"use client";

// react-pdf viewer with span-level citation highlight — the wow moment.
// Click an obligation → we scroll to the cited page and the exact sentence
// glows in the text layer. Client-only (loaded via next/dynamic, ssr:false).

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { findQuoteRanges, renderItemHtml, type ItemRange } from "@/lib/highlight";
import type { CiteTarget } from "@/lib/types";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

interface Props {
  pdfUrl: string;
  cite: CiteTarget | null;
  onError: () => void; // parent falls back to the iframe viewer
}

export default function PdfViewer({ pdfUrl, cite, onError }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const [numPages, setNumPages] = useState(0);
  const [width, setWidth] = useState(0);
  // Per-page text items, captured as each text layer loads.
  const [pageItems, setPageItems] = useState<Record<number, string[]>>({});

  // Fit pages to the pane, re-measuring on resize/collapse.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Which items glow on the cited page.
  const ranges: ItemRange[] = useMemo(() => {
    if (!cite?.quote || !cite.page) return [];
    const items = pageItems[cite.page];
    if (!items) return [];
    return findQuoteRanges(items, cite.quote);
  }, [cite, pageItems]);

  // Scroll to the cited page, then center the glowing sentence.
  useEffect(() => {
    if (!cite?.page) return;
    pageRefs.current[cite.page]?.scrollIntoView({ behavior: "smooth", block: "start" });
    const t = setTimeout(() => {
      containerRef.current
        ?.querySelector(".anvil-glow")
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 450);
    return () => clearTimeout(t);
  }, [cite, ranges.length]);

  const textRenderer = useCallback(
    ({ str, itemIndex, pageNumber }: { str: string; itemIndex: number; pageNumber: number }) => {
      if (!cite?.page || pageNumber !== cite.page || ranges.length === 0) {
        return renderItemHtml(str, [], itemIndex);
      }
      return renderItemHtml(str, ranges, itemIndex);
    },
    [cite, ranges]
  );

  return (
    <div ref={containerRef} className="h-full w-full overflow-y-auto bg-[#f5f7f9]">
      <Document
        file={pdfUrl}
        onLoadSuccess={(doc) => setNumPages(doc.numPages)}
        onLoadError={onError}
        loading={
          <p className="p-6 text-sm text-[#51606f]" role="status">
            Loading the document…
          </p>
        }
        error={<p className="p-6 text-sm text-[#9a6a1e]">Could not render the PDF.</p>}
      >
        {width > 0 &&
          Array.from({ length: numPages }, (_, i) => i + 1).map((n) => (
            <div
              key={n}
              ref={(el) => {
                pageRefs.current[n] = el;
              }}
              className="mx-auto mb-3 w-fit border border-[#d7dee6] bg-white shadow-sm"
              data-page={n}
            >
              <Page
                pageNumber={n}
                width={Math.min(width - 24, 900)}
                customTextRenderer={textRenderer}
                onGetTextSuccess={({ items }) => {
                  setPageItems((m) => ({
                    ...m,
                    [n]: items.map((it) => ("str" in it ? it.str : "")),
                  }));
                }}
                renderAnnotationLayer={false}
              />
            </div>
          ))}
      </Document>
    </div>
  );
}

"use client";

// The right pane: the source document itself, collapsible (modeled on
// Claude's dual view — work on the left, source on the right).
// v1 uses the browser's native PDF viewer via <iframe>; citation clicks
// jump it to the cited page with #page=N. Upgrade path (Wk7): react-pdf
// with span-level highlight boxes — swap only this component.
// Sizing/visibility is owned by the workspace wrapper; collapse is a
// desktop-only affordance (phones switch panes instead).

interface Props {
  pdfUrl: string;
  page: number | null;       // set by "View in document" clicks
  collapsed: boolean;
  onToggle: () => void;
}

export default function DocumentPane({ pdfUrl, page, collapsed, onToggle }: Props) {
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

  const src = page ? `${pdfUrl}#page=${page}` : pdfUrl;

  return (
    <div className="flex h-full w-full flex-col border-[#d7dee6] bg-white lg:border-l">
      <div className="flex items-center justify-between border-b border-[#d7dee6] px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-[#51606f]">
          Source document {page ? `· p.${page}` : ""}
        </span>
        <button
          onClick={onToggle}
          className="hidden text-xs text-[#16324f] underline underline-offset-2 hover:text-[#0f2438] lg:block"
        >
          Collapse
        </button>
      </div>
      {/* key={src} forces the iframe to honor page jumps on re-cite */}
      <iframe key={src} src={src} title="Source document" className="h-full w-full" />
    </div>
  );
}

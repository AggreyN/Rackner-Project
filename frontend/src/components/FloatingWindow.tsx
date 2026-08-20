"use client";

// A small draggable, resizable window — no library, ~40 lines of pointer
// math. Pointer capture keeps move events flowing even when a fast drag
// outruns the header; touch-action:none stops mobile browsers from
// scrolling the page instead of dragging. Position is clamped to the
// viewport so the window can never be dragged somewhere unrecoverable.

import { useCallback, useEffect, useRef, useState } from "react";

const MIN_W = 300;
const MIN_H = 280;
const MARGIN = 8; // keep at least this much of the window on-screen

interface Props {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  /** Initial placement; defaults to bottom-left, above the launcher. */
  initial?: { x: number; y: number; w: number; h: number };
}

export default function FloatingWindow({ title, onClose, children, initial }: Props) {
  const [box, setBox] = useState(() => {
    if (initial) return initial;
    const w = 360;
    const h = 420;
    return {
      x: 16,
      y: typeof window === "undefined" ? 120 : Math.max(window.innerHeight - h - 84, MARGIN),
      w,
      h,
    };
  });

  const clamp = useCallback((b: { x: number; y: number; w: number; h: number }) => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const w = Math.min(Math.max(b.w, MIN_W), vw - MARGIN * 2);
    const h = Math.min(Math.max(b.h, MIN_H), vh - MARGIN * 2);
    return {
      w,
      h,
      x: Math.min(Math.max(b.x, MARGIN), vw - w - MARGIN),
      y: Math.min(Math.max(b.y, MARGIN), vh - h - MARGIN),
    };
  }, []);

  // If the browser window shrinks, pull the chat window back on-screen.
  useEffect(() => {
    const onResize = () => setBox((b) => clamp(b));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [clamp]);

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const drag = useRef<{ dx: number; dy: number } | null>(null);
  const resize = useRef<{ px: number; py: number; w: number; h: number } | null>(null);

  return (
    <div
      role="dialog"
      aria-label={title}
      data-testid="floating-window"
      className="fixed z-40 flex flex-col overflow-hidden rounded-lg border border-[#d7dee6] bg-white shadow-[0_10px_40px_rgba(22,50,79,.25)]"
      style={{ left: box.x, top: box.y, width: box.w, height: box.h }}
    >
      <div
        data-testid="floating-window-header"
        className="flex shrink-0 cursor-move select-none items-center justify-between border-b border-[#d7dee6] bg-[#16324f] px-3 py-2 [touch-action:none]"
        onPointerDown={(e) => {
          // Pointer capture redirects the pointerup, which suppresses click
          // on children — so a press on the ✕ must never start a drag.
          if ((e.target as HTMLElement).closest("button")) return;
          drag.current = { dx: e.clientX - box.x, dy: e.clientY - box.y };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const { dx, dy } = drag.current;
          setBox((b) => clamp({ ...b, x: e.clientX - dx, y: e.clientY - dy }));
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
      >
        <span className="text-xs font-semibold uppercase tracking-widest text-white">
          {title}
        </span>
        <button
          onClick={onClose}
          aria-label="Close"
          data-testid="floating-window-close"
          className="rounded px-1.5 text-white/80 hover:bg-white/10 hover:text-white"
        >
          ✕
        </button>
      </div>

      <div className="min-h-0 flex-1">{children}</div>

      {/* bottom-right resize grip */}
      <div
        data-testid="floating-window-resize"
        aria-hidden
        className="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize [touch-action:none]"
        onPointerDown={(e) => {
          resize.current = { px: e.clientX, py: e.clientY, w: box.w, h: box.h };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!resize.current) return;
          const { px, py, w, h } = resize.current;
          setBox((b) => clamp({ ...b, w: w + (e.clientX - px), h: h + (e.clientY - py) }));
        }}
        onPointerUp={() => {
          resize.current = null;
        }}
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4 text-[#51606f]">
          <path d="M14 8L8 14M14 12l-2 2" stroke="currentColor" strokeWidth="1.5" fill="none" />
        </svg>
      </div>
    </div>
  );
}

"use client";

// Presentational drop zone — the intake choreography (validate → scan →
// PII modal → upload) lives in useDocumentIntake, shared with SamIntake.

import { useRef, useState } from "react";
import { MAX_UPLOAD_MB } from "@/hooks/useDocumentIntake";
import { DEMO_PDF_PATH } from "@/lib/mock";

interface Props {
  onFile: (file: File) => void;
  busy: string | null;
  error: string | null;
}

export default function UploadZone({ onFile, busy, error }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  // The seeded demo document (its page 1 carries a POC email + phone, so
  // the PII confirmation flow always fires) — one click, no file hunting.
  async function loadDemoDoc() {
    const res = await fetch(DEMO_PDF_PATH);
    const blob = await res.blob();
    onFile(
      new File([blob], "TeamAnvil-Demo-Solicitation.pdf", { type: "application/pdf" })
    );
  }

  return (
    <div>
      <div
        onClick={() => !busy && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f && !busy) onFile(f);
        }}
        className={
          "cursor-pointer border border-dashed bg-white p-10 text-center " +
          (dragOver ? "border-[#16324f] bg-[#f5f7f9]" : "border-[#16324f]/40 hover:border-[#16324f]")
        }
      >
        <p className="text-sm font-medium text-[#16324f]">
          Drop a federal contract or solicitation PDF here
        </p>
        <p className="mt-1 text-xs text-[#51606f]">
          or click to browse · PDF only · up to {MAX_UPLOAD_MB} MB · auto-deleted after 3 days
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
            e.target.value = ""; // allow re-selecting the same file
          }}
        />
      </div>

      <div className="mt-2 text-xs text-[#51606f]">
        No document handy?{" "}
        <button
          onClick={() => void loadDemoDoc()}
          disabled={!!busy}
          className="font-medium text-[#16324f] underline underline-offset-2 hover:text-[#0f2438] disabled:opacity-50"
        >
          Use the seeded demo solicitation
        </button>
      </div>

      {busy && (
        <p className="mt-3 text-sm text-[#51606f]" role="status">
          <span className="mr-2 inline-block h-2 w-2 animate-pulse bg-[#16324f]" aria-hidden />
          {busy}
        </p>
      )}
      {error && (
        <p className="mt-3 border border-[#9a6a1e]/40 bg-[#9a6a1e]/5 px-3 py-2 text-sm text-[#9a6a1e]" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

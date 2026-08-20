"use client";

// Import a contract PDF that couldn't be found on SAM.gov. The document
// goes through the same pipeline as a SAM pull — parse, section, analyze,
// verify quotes — and lands in the same split-pane workspace.

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { importOpportunityPdf } from "@/lib/api";

export default function ImportPdf() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    setBusy(`Reading ${file.name}…`);
    try {
      const opp = await importOpportunityPdf(file);
      router.push(`/opportunity/${opp.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  }

  return (
    <div className="inline-flex flex-col">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy !== null}
        data-testid="import-pdf"
        className="rounded-lg border border-[#d7dee6] bg-white px-4 py-3 text-sm font-semibold text-[#16324f] hover:border-[#16324f] disabled:opacity-60"
        title="Analyze a contract that isn't on SAM.gov"
      >
        {busy ?? "⇪ Import PDF"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleFile(f);
          e.target.value = ""; // allow re-importing the same file
        }}
      />
      {error && <p className="mt-1.5 text-xs text-[#a3231f]">{error}</p>}
    </div>
  );
}

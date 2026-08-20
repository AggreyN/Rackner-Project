"use client";

// The Opportunity Lifecycle plan is the yardstick every opportunity is
// scored against (build plan §1 step 2). This modal shows the parsed "fit
// profile" and lets the user upload/replace the plan PDF. Optional in the
// flow, but scoring and suggestions depend on it.

import { useRef, useState } from "react";
import { deleteLifecyclePlan, uploadLifecyclePlan } from "@/lib/api";
import type { LifecycleProfile } from "@/lib/types";

interface Props {
  lifecycle: LifecycleProfile | null;
  onClose: () => void;
  onUpdated: () => void;
}

export default function LifecycleModal({ lifecycle, onClose, onUpdated }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    if (file.type !== "application/pdf") {
      setError("Upload the lifecycle plan as a PDF.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await uploadLifecyclePlan(file);
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove() {
    setError(null);
    setBusy(true);
    try {
      await deleteLifecyclePlan();
      onUpdated(); // lists go neutral — no scores until a new plan lands
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#16324f]/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md border border-[#d7dee6] bg-white p-6 shadow-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-[#16324f]">Opportunity Lifecycle plan</h2>
        <p className="mt-1 text-sm text-[#51606f]">
          Parsed once into your fit profile — the yardstick every opportunity is scored against.
        </p>

        {lifecycle ? (
          <div className="mt-4 space-y-3 text-sm">
            <div className="flex items-center justify-between border border-[#d7dee6] px-3 py-2">
              <span className="truncate font-medium text-[#16324f]">{lifecycle.filename}</span>
              <span className="ml-3 shrink-0 text-xs text-[#1e7a46]">✓ on file</span>
            </div>
            <ProfileRow label="Capabilities" values={lifecycle.capabilities} />
            <ProfileRow label="NAICS" values={lifecycle.naics_codes} />
            <ProfileRow label="Target agencies" values={lifecycle.target_agencies} />
            <ProfileRow label="Set-asides" values={lifecycle.set_asides} />
          </div>
        ) : (
          <p className="mt-4 border border-dashed border-[#d7dee6] bg-[#f5f7f9] p-4 text-sm text-[#51606f]">
            No plan on file yet — suggested opportunities won&apos;t have fit scores until one is
            uploaded.
          </p>
        )}

        {error && <p className="mt-3 text-sm text-[#a3231f]">{error}</p>}

        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            onClick={onClose}
            className="border border-[#d7dee6] px-4 py-2 text-sm text-[#16324f] hover:bg-[#f5f7f9]"
          >
            Close
          </button>
          {lifecycle && (
            <button
              onClick={handleRemove}
              disabled={busy}
              data-testid="remove-plan"
              title="Search and suggestions go neutral (unscored) until a new plan is uploaded"
              className="border border-[#d7dee6] px-3 py-2 text-sm text-[#a3231f] hover:bg-[#f9e8e7] disabled:opacity-60"
            >
              Remove plan
            </button>
          )}
          <button
            onClick={() => inputRef.current?.click()}
            disabled={busy}
            className="bg-[#16324f] px-4 py-2 text-sm font-medium text-white hover:bg-[#0f2438] disabled:opacity-60"
          >
            {busy ? "Parsing plan…" : lifecycle ? "Replace plan (PDF)" : "Upload plan (PDF)"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
            }}
          />
        </div>
      </div>
    </div>
  );
}

function ProfileRow({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <span
            key={v}
            className="rounded-full border border-[#d7dee6] bg-[#f5f7f9] px-2 py-0.5 text-xs text-[#16324f]"
          >
            {v}
          </span>
        ))}
      </div>
    </div>
  );
}

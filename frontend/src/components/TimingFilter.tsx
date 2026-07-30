"use client";

// Timing filter — the recompete radar's front door.
//
// Why this exists: by the time a solicitation posts on SAM.gov, the capture
// window is mostly gone; the incumbent has already shaped the requirement.
// Capture people work backwards from CONTRACT EXPIRY instead, and 12–18
// months out is the sweet spot — late enough that the recompete is real,
// early enough to influence it. That preset is the default entry point.

import type { SearchFilters, TimingPreset } from "@/lib/types";
import { TIMING_PRESETS } from "@/lib/types";

interface Props {
  active: TimingPreset;
  onChange: (preset: TimingPreset, filters: SearchFilters) => void;
}

export default function TimingFilter({ active, onChange }: Props) {
  const current = TIMING_PRESETS.find((p) => p.key === active);

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-[#51606f]">
          Timing
        </span>
        {TIMING_PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => onChange(p.key, p.filters)}
            aria-pressed={active === p.key}
            data-testid={`timing-${p.key}`}
            className={
              "rounded-full border px-3 py-1 text-xs transition-colors " +
              (active === p.key
                ? "border-[#16324f] bg-[#16324f] text-white"
                : "border-[#d7dee6] bg-white text-[#16324f] hover:border-[#16324f]")
            }
          >
            {p.label}
          </button>
        ))}
      </div>
      {current && current.key !== "all" && (
        <p className="mt-1.5 text-xs leading-relaxed text-[#51606f]">{current.hint}</p>
      )}
    </div>
  );
}

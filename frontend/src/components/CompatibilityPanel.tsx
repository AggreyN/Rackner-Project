"use client";

// The compatibility score vs. the lifecycle plan — the intellectual core
// (build plan §2). Donut = weighted 0–100 score; bars = the 8 CAP-derived
// factors, each 1–5 with weight and a cited rationale. Bands mirror the
// CAP bid/no-bid thresholds: ≥70 pursue · 50–69 conditional · <50 no-bid.

import type { Analysis, FitFactor } from "@/lib/types";
import { BAND_LABELS } from "@/lib/types";
import { bandColor } from "./ScoreBadge";

const BAND_BG: Record<string, string> = {
  pursue: "#e3f2ea",
  conditional: "#fbf4e6",
  no_bid: "#f9e8e7",
};

export default function CompatibilityPanel({
  analysis,
  onCite,
}: {
  analysis: Analysis;
  onCite: (quoteRef: { section: string }) => void;
}) {
  const color = bandColor(analysis.score);
  const r = 50;
  const circumference = 2 * Math.PI * r;
  const arc = (analysis.score / 100) * circumference;

  return (
    <div className="border border-[#d7dee6] bg-white p-4 sm:p-5">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
        Compatibility vs. your lifecycle plan
      </h3>
      <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
        <div className="relative h-[120px] w-[120px] shrink-0" data-testid="fit-donut">
          <svg width="120" height="120" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r={r} fill="none" stroke="#eef2f6" strokeWidth="14" />
            <circle
              cx="60"
              cy="60"
              r={r}
              fill="none"
              stroke={color}
              strokeWidth="14"
              strokeDasharray={`${arc} ${circumference}`}
              strokeLinecap="round"
              transform="rotate(-90 60 60)"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <b className="text-[26px] text-[#16324f]">{analysis.score}</b>
            <small className="text-[10px] uppercase tracking-wide text-[#51606f]">
              {BAND_LABELS[analysis.band]}
            </small>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <span
            className="mb-2.5 inline-block rounded-full px-2.5 py-0.5 text-xs font-bold"
            style={{ color, backgroundColor: BAND_BG[analysis.band] }}
          >
            {analysis.verdict}
          </span>
          <div className="space-y-1.5">
            {analysis.factors.map((f) => (
              <FactorRow key={f.key} factor={f} onCite={onCite} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function FactorRow({
  factor: f,
  onCite,
}: {
  factor: FitFactor;
  onCite: (quoteRef: { section: string }) => void;
}) {
  return (
    <div
      className="group flex items-center gap-2.5 text-xs"
      title={`${f.rationale}${f.citation ? ` (${f.citation.section})` : ""} · weight ${Math.round(f.weight * 100)}%`}
    >
      <span className="w-[46%] truncate text-[#1f2933] sm:w-[170px]">{f.label}</span>
      <div className="h-[7px] flex-1 overflow-hidden rounded-full bg-[#f5f7f9]">
        <i
          className="block h-full rounded-full bg-[#16324f]"
          style={{ width: `${(f.score / 5) * 100}%` }}
        />
      </div>
      <span className="w-7 text-right text-[11px] text-[#51606f]">{f.score.toFixed(1)}</span>
      {f.citation ? (
        <button
          onClick={() => onCite({ section: f.citation!.section })}
          className="w-10 text-left text-[10px] text-[#16324f] underline-offset-2 hover:underline"
          title={`View ${f.citation.section} in the source`}
        >
          {f.citation.section}
        </button>
      ) : (
        <span className="w-10" />
      )}
    </div>
  );
}

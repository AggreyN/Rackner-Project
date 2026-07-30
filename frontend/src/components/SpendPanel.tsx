"use client";

// Spend history from USAspending.gov — "how much money is really behind
// it?" Mini bar chart of obligations by fiscal year plus incumbent + trend.

import type { SpendSummary } from "@/lib/types";

function fmtMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${n}`;
}

export default function SpendPanel({ spend }: { spend: SpendSummary }) {
  const max = Math.max(...spend.years.map((y) => y.amount), 1);

  return (
    <div className="border border-[#d7dee6] bg-white p-4 sm:p-5" data-testid="spend-panel">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
        Spend history · USAspending.gov
      </h3>

      {spend.years.length === 0 ? (
        <p className="text-sm text-[#51606f]">
          No prior award history found — this looks like a new requirement.
        </p>
      ) : (
        <>
          <div className="mb-2 mt-5 flex h-[70px] items-end gap-2">
            {spend.years.map((y) => (
              <div key={y.fiscal_year} className="relative flex-1">
                <div
                  className="rounded-t-[3px] bg-[#16324f]"
                  style={{ height: `${Math.max((y.amount / max) * 70, 4)}px` }}
                />
                <span className="absolute -top-4 left-0 right-0 text-center text-[9px] text-[#51606f]">
                  {fmtMoney(y.amount)}
                </span>
                <span className="absolute -bottom-4 left-0 right-0 text-center text-[9px] text-[#51606f]">
                  {y.fiscal_year}
                </span>
              </div>
            ))}
          </div>
          <div className="h-4" />
        </>
      )}

      <div className="divide-y divide-[#f5f7f9] text-[12.5px]">
        <div className="flex justify-between py-1.5">
          <span className="text-[#51606f]">Total obligated (prior contract)</span>
          <b className="text-[#16324f]">{fmtMoney(spend.total_obligated)}</b>
        </div>
        <div className="flex justify-between gap-3 py-1.5">
          <span className="text-[#51606f]">Incumbent</span>
          <b className="truncate text-right text-[#16324f]">
            {spend.incumbent ? `${spend.incumbent.name} · UEI ${spend.incumbent.uei}` : "None"}
          </b>
        </div>
        {spend.trend_pct !== null && (
          <div className="flex justify-between py-1.5">
            <span className="text-[#51606f]">Trend</span>
            <b style={{ color: spend.trend_pct >= 0 ? "#1e7a46" : "#a3231f" }}>
              {spend.trend_pct >= 0 ? "↑ growing" : "↓ declining"} ~{Math.abs(spend.trend_pct)}
              %/yr
            </b>
          </div>
        )}
      </div>
    </div>
  );
}

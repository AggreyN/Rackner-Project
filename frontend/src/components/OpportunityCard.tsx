"use client";

// One SAM.gov opportunity in the search/suggested grid: title, agency line,
// mini description, closing/value/incumbent meta, and the fit-score badge.

import Link from "next/link";
import type { OpportunitySummary } from "@/lib/types";
import ScoreBadge from "./ScoreBadge";

export default function OpportunityCard({ opp }: { opp: OpportunitySummary }) {
  const agencyLine = [opp.agency, opp.office, opp.naics ? `NAICS ${opp.naics}` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <Link
      href={`/opportunity/${opp.id}`}
      data-testid="opportunity-card"
      className="block border border-[#d7dee6] bg-white p-4 transition-colors hover:border-[#16324f] hover:shadow-[0_4px_14px_rgba(22,50,79,.08)] sm:p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-[15px] font-semibold leading-snug text-[#16324f]">{opp.title}</h4>
          <div className="mt-0.5 text-xs text-[#51606f]">{agencyLine}</div>
        </div>
        <ScoreBadge score={opp.fit_score} />
      </div>

      <p className="mt-2 text-[13px] leading-relaxed text-[#1f2933]">{opp.description}</p>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-[#51606f]">
        {opp.days_to_close !== null && (
          <span>
            ⏱ {opp.kind === "baa" ? `AOI in ${opp.days_to_close} days` : `Closes in ${opp.days_to_close} days`}
          </span>
        )}
        {opp.est_value && <span>💲 Est. {opp.est_value}</span>}
        <span>{opp.incumbent ? `Incumbent: ${opp.incumbent}` : "Incumbent: none (new)"}</span>
      </div>
    </Link>
  );
}

"use client";

// One opportunity in the search/suggested grid. Two flavors:
//   · solicitation — posted on SAM.gov, shows the response deadline
//   · expiring_award — an existing award from USAspending nearing its period
//     of performance end, i.e. a recompete you can still shape. Shows months
//     to expiry instead of a close date, plus whether it's inside the 12–18
//     month capture window.

import Link from "next/link";
import type { OpportunitySummary } from "@/lib/types";
import { RECOMPETE_WINDOW } from "@/lib/types";
import ScoreBadge from "./ScoreBadge";

function inCaptureWindow(months: number): boolean {
  return months >= RECOMPETE_WINDOW.from && months <= RECOMPETE_WINDOW.to;
}

export default function OpportunityCard({ opp }: { opp: OpportunitySummary }) {
  const agencyLine = [opp.agency, opp.office, opp.naics ? `NAICS ${opp.naics}` : null]
    .filter(Boolean)
    .join(" · ");

  const isRecompete = opp.kind === "expiring_award" && opp.months_to_expiry !== null;
  const months = opp.months_to_expiry ?? 0;

  return (
    <Link
      href={`/opportunity/${opp.id}`}
      data-testid="opportunity-card"
      data-kind={opp.kind}
      className="block border border-[#d7dee6] bg-white p-4 transition-colors hover:border-[#16324f] hover:shadow-[0_4px_14px_rgba(22,50,79,.08)] sm:p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {isRecompete && (
            <span
              data-testid="recompete-tag"
              className={
                "mb-1 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide " +
                (inCaptureWindow(months)
                  ? "bg-[#e3f2ea] text-[#1e7a46]"
                  : "bg-[#f5f7f9] text-[#51606f]")
              }
            >
              {inCaptureWindow(months) ? "◎ Capture window" : "Expiring award"}
            </span>
          )}
          <h4 className="text-[15px] font-semibold leading-snug text-[#16324f]">{opp.title}</h4>
          <div className="mt-0.5 text-xs text-[#51606f]">{agencyLine}</div>
        </div>
        <ScoreBadge score={opp.fit_score} />
      </div>

      <p className="mt-2 text-[13px] leading-relaxed text-[#1f2933]">{opp.description}</p>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-[#51606f]">
        {isRecompete ? (
          <span
            className={inCaptureWindow(months) ? "font-semibold text-[#1e7a46]" : undefined}
            title={opp.expiry_date ? `Period of performance ends ${opp.expiry_date}` : undefined}
          >
            ⏳ Expires in {months} months
          </span>
        ) : (
          opp.days_to_close !== null && (
            <span>
              ⏱{" "}
              {opp.kind === "baa"
                ? `AOI in ${opp.days_to_close} days`
                : `Closes in ${opp.days_to_close} days`}
            </span>
          )
        )}
        {opp.est_value && <span>💲 {opp.est_value}</span>}
        <span>{opp.incumbent ? `Incumbent: ${opp.incumbent}` : "Incumbent: none (new)"}</span>
      </div>
    </Link>
  );
}

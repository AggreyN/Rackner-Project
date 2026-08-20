// Circular fit-score badge on opportunity cards. Color = band:
// green ≥70 (pursue) · amber 50–69 (conditional) · red <50 (likely no-bid).
// Mirrors the CAP bid/no-bid thresholds.
//
// Estimates vs verdicts: a metadata-only pre-screen (fit_source="estimate")
// renders approximate — "~69" with an "est." label and a dashed ring — while
// a real analysis score (fit_source="analysis") renders solid. An estimate
// must never masquerade as the researched number: a shallow "44" could hide
// a genuine "89" behind an unclicked card.

interface Props {
  score: number | null;
  source?: "estimate" | "analysis" | null;
}

export function bandColor(score: number): string {
  if (score >= 70) return "#1e7a46";
  if (score >= 50) return "#9a6a1e";
  return "#a3231f";
}

export default function ScoreBadge({ score, source }: Props) {
  if (score === null) {
    return (
      <div
        title="Upload a lifecycle plan to score opportunities"
        className="flex h-[54px] w-[54px] shrink-0 flex-col items-center justify-center rounded-full border border-dashed border-[#d7dee6] text-[#51606f]"
      >
        <span className="text-sm font-bold">—</span>
        <span className="text-[8px] font-semibold uppercase">fit</span>
      </div>
    );
  }
  const isEstimate = source !== "analysis";
  if (isEstimate) {
    return (
      <div
        title="Quick estimate from the notice card — open the opportunity for the full analysis"
        data-testid="fit-estimate"
        className="flex h-[54px] w-[54px] shrink-0 flex-col items-center justify-center rounded-full border-2 border-dashed bg-white font-bold"
        style={{ borderColor: bandColor(Math.round(score)), color: bandColor(Math.round(score)) }}
      >
        <span className="text-base leading-none">~{Math.round(score)}</span>
        <span className="mt-0.5 text-[8px] font-semibold uppercase opacity-85">est.</span>
      </div>
    );
  }
  return (
    <div
      title="Score from your full analysis of this opportunity"
      data-testid="fit-analyzed"
      className="flex h-[54px] w-[54px] shrink-0 flex-col items-center justify-center rounded-full font-bold text-white"
      style={{ backgroundColor: bandColor(Math.round(score)) }}
    >
      <span className="text-base leading-none">{Math.round(score)}</span>
      <span className="mt-0.5 text-[8px] font-semibold uppercase opacity-85">fit</span>
    </div>
  );
}

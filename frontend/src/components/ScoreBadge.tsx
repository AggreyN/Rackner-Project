// Circular fit-score badge on opportunity cards. Color = band:
// green ≥70 (pursue) · amber 50–69 (conditional) · red <50 (likely no-bid).
// Mirrors the CAP bid/no-bid thresholds.

interface Props {
  score: number | null;
}

export function bandColor(score: number): string {
  if (score >= 70) return "#1e7a46";
  if (score >= 50) return "#9a6a1e";
  return "#a3231f";
}

export default function ScoreBadge({ score }: Props) {
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
  return (
    <div
      className="flex h-[54px] w-[54px] shrink-0 flex-col items-center justify-center rounded-full font-bold text-white"
      style={{ backgroundColor: bandColor(score) }}
    >
      <span className="text-base leading-none">{score}</span>
      <span className="mt-0.5 text-[8px] font-semibold uppercase opacity-85">fit</span>
    </div>
  );
}

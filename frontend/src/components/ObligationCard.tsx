import type { Obligation } from "@/types/obligation";

// Pick a badge color based on the obligation type.
function typeColor(type: string): string {
  switch (type) {
    case "Reporting":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300";
    case "Deliverable":
      return "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300";
    case "Compliance":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300";
    default:
      return "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300";
  }
}

export function ObligationCard({ obligation }: { obligation: Obligation }) {
  return (
    <article className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      {/* Top row: type badge + confidence */}
      <div className="mb-2 flex items-center justify-between">
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${typeColor(obligation.type)}`}>
          {obligation.type}
        </span>
        <span className="text-xs text-zinc-400">
          {Math.round(obligation.confidence * 100)}% confidence
        </span>
      </div>

      {/* The plain-English obligation */}
      <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
        {obligation.text}
      </p>

      {/* Metadata row */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
        <span>📅 {obligation.deadline ?? "No deadline"}</span>
        <span>👤 {obligation.responsibleParty}</span>
        <span>§ {obligation.sourceClauseId} · p.{obligation.page}</span>
      </div>

      {/* Verbatim source quote (the "citation" that makes it verifiable) */}
      <blockquote className="mt-3 border-l-2 border-zinc-300 pl-3 text-xs italic text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
        “{obligation.verbatimQuote}”
      </blockquote>
    </article>
  );
}

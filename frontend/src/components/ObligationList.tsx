"use client";

// The left pane: obligations grouped by time / category / type,
// filtered-and-sorted for the chosen role. Items outside the role are
// dimmed, never hidden. Header tracks review progress and exports CSV.

import type { Obligation, ObligationGroups } from "@/lib/types";
import { TIME_BUCKET_LABELS } from "@/lib/types";
import { downloadCsv, registerToCsv } from "@/lib/csv";
import ObligationCard from "./ObligationCard";

interface Props {
  data: ObligationGroups | null;
  error: string | null;
  onRetry: () => void;
  groupBy: string;
  onGroupBy: (g: string) => void;
  onCite: (page: number, quote: string | null) => void;
  statusOverrides: Record<number, Obligation["status"]>;
  onStatusChange: (id: number, next: Obligation["status"], prev: Obligation["status"]) => void;
  exportName: string;
}

const GROUPINGS = [
  { key: "time", label: "By time" },
  { key: "category", label: "By category" },
  { key: "type", label: "By type" },
];

export default function ObligationList({
  data,
  error,
  onRetry,
  groupBy,
  onGroupBy,
  onCite,
  statusOverrides,
  onStatusChange,
  exportName,
}: Props) {
  if (error) {
    return (
      <div className="flex h-full w-full items-center justify-center p-6">
        <div className="max-w-sm border border-[#9a6a1e]/40 bg-white p-5 text-center">
          <p className="text-sm font-semibold text-[#16324f]">
            Couldn&apos;t load the register
          </p>
          <p className="mt-1 text-xs text-[#51606f]">{error}</p>
          <button
            onClick={onRetry}
            className="mt-3 bg-[#16324f] px-4 py-1.5 text-sm text-white hover:bg-[#0f2438]"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    // Skeleton register — same silhouette as the loaded cards.
    return (
      <div className="w-full space-y-4 p-4" role="status" aria-label="Loading obligations">
        <div className="h-8 w-1/2 animate-pulse bg-[#d7dee6]/60" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-2 border border-[#d7dee6] bg-white p-4">
            <div className="h-4 w-5/6 animate-pulse bg-[#d7dee6]/60" />
            <div className="h-3 w-2/3 animate-pulse bg-[#d7dee6]/50" />
            <div className="h-10 w-full animate-pulse bg-[#f5f7f9]" />
          </div>
        ))}
      </div>
    );
  }

  const groupNames = Object.keys(data.groups);
  const all = groupNames.flatMap((n) => data.groups[n]);
  const statusOf = (o: Obligation) => statusOverrides[o.id] ?? o.status;
  const relevant = all.filter((o) => o.relevant_to_role).length;
  const dimmed = data.total - relevant;
  const inReview = all.filter((o) => statusOf(o) === "in-review").length;
  const done = all.filter((o) => statusOf(o) === "done").length;

  function exportCsv() {
    const withStatus = all.map((o) => ({ ...o, status: statusOf(o) }));
    downloadCsv(exportName, registerToCsv(withStatus));
  }

  return (
    <div className="flex h-full w-full flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#d7dee6] bg-white px-4 py-3">
        <div className="min-w-0">
          <span className="text-sm font-semibold text-[#16324f]">
            {data.total} obligations
          </span>
          <span className="ml-2 text-xs text-[#51606f]">
            {dimmed > 0 && <>{relevant} for your role · </>}
            {inReview} in review · {done} done
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex border border-[#d7dee6]" role="tablist" aria-label="Group obligations">
            {GROUPINGS.map((g) => (
              <button
                key={g.key}
                role="tab"
                aria-selected={groupBy === g.key}
                onClick={() => onGroupBy(g.key)}
                className={
                  "px-3 py-1 text-xs " +
                  (groupBy === g.key
                    ? "bg-[#16324f] text-white"
                    : "bg-white text-[#16324f] hover:bg-[#f5f7f9]")
                }
              >
                {g.label}
              </button>
            ))}
          </div>
          <button
            onClick={exportCsv}
            className="border border-[#16324f] px-3 py-1 text-xs text-[#16324f] hover:bg-[#16324f] hover:text-white"
          >
            Export CSV
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-4">
        {groupNames.map((name) => (
          <section key={name}>
            <h3 className="sticky -top-4 z-10 -mx-1 mb-2 bg-[#f5f7f9] px-1 py-1 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
              {TIME_BUCKET_LABELS[name] ?? name.replace(/_/g, " ")}
              <span className="ml-2 font-normal normal-case">
                ({data.groups[name].length})
              </span>
            </h3>
            <div className="space-y-3">
              {data.groups[name].map((o) => (
                <ObligationCard
                  key={o.id}
                  obligation={o}
                  status={statusOf(o)}
                  onStatusChange={onStatusChange}
                  onCite={onCite}
                />
              ))}
            </div>
          </section>
        ))}
        {groupNames.length === 0 && (
          <div className="border border-[#d7dee6] bg-white p-6 text-center">
            <p className="text-sm font-semibold text-[#16324f]">
              No obligations found in this document
            </p>
            <p className="mt-1 text-xs text-[#51606f]">
              That can happen with cover letters, amendments without clauses, or
              image-only scans. Try another document — or another grouping.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

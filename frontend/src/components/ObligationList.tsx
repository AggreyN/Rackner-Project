"use client";

// The left pane: obligations grouped by time / category / type,
// filtered-and-sorted for the chosen role.

import type { ObligationGroups } from "../lib/types";
import { TIME_BUCKET_LABELS } from "../lib/types";
import ObligationCard from "./ObligationCard";

interface Props {
  data: ObligationGroups | null;
  groupBy: string;
  onGroupBy: (g: string) => void;
  onCite: (page: number | null) => void;
}

const GROUPINGS = [
  { key: "time", label: "By time" },
  { key: "category", label: "By category" },
  { key: "type", label: "By type" },
];

export default function ObligationList({ data, groupBy, onGroupBy, onCite }: Props) {
  if (!data) {
    return <p className="p-6 text-sm text-[#51606f]">Reading the document…</p>;
  }

  const groupNames = Object.keys(data.groups);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-[#d7dee6] bg-white px-4 py-3">
        <span className="text-sm font-semibold text-[#16324f]">
          {data.total} obligations
        </span>
        <div className="flex border border-[#d7dee6]">
          {GROUPINGS.map((g) => (
            <button
              key={g.key}
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
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-4">
        {groupNames.map((name) => (
          <section key={name}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
              {TIME_BUCKET_LABELS[name] ?? name.replace(/_/g, " ")}
              <span className="ml-2 font-normal normal-case">
                ({data.groups[name].length})
              </span>
            </h3>
            <div className="space-y-3">
              {data.groups[name].map((o) => (
                <ObligationCard key={o.id} obligation={o} onCite={onCite} />
              ))}
            </div>
          </section>
        ))}
        {groupNames.length === 0 && (
          <p className="text-sm text-[#51606f]">No obligations extracted yet.</p>
        )}
      </div>
    </div>
  );
}

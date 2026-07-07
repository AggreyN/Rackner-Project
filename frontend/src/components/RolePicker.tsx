"use client";

// "Choose your role, get your answers" — the core of the intelligence-layer
// pitch. Each card shows the question that team asks of a document.

import type { RoleInfo } from "@/lib/types";

interface Props {
  roles: RoleInfo[];
  selected: string | null;
  onSelect: (key: string) => void;
}

export default function RolePicker({ roles, selected, onSelect }: Props) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {roles.map((r) => {
        const active = selected === r.key;
        return (
          <button
            key={r.key}
            onClick={() => onSelect(r.key)}
            className={
              "border p-4 text-left transition-colors " +
              (active
                ? "border-[#16324f] bg-[#16324f] text-white"
                : "border-[#d7dee6] bg-white text-[#16324f] hover:border-[#16324f]")
            }
          >
            <div className="text-sm font-semibold">{r.label}</div>
            <div className={"mt-1 text-xs " + (active ? "text-white/75" : "text-[#51606f]")}>
              {r.question}
            </div>
          </button>
        );
      })}
    </div>
  );
}

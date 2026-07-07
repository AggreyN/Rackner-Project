"use client";

// SAM.gov intake: search public solicitations and pull one straight into
// the app — the pulled PDF goes through the exact same scan → PII → upload
// flow as a dropped file (via the shared onFile handler).

import { useState } from "react";

interface SamResult {
  noticeId: string;
  title: string;
  solicitationNumber: string;
  postedDate: string;
  attachmentUrl: string;
}

interface Props {
  onFile: (file: File) => void;
  disabled: boolean;
}

export default function SamIntake({ onFile, disabled }: Props) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SamResult[] | null>(null);
  const [mock, setMock] = useState(false);
  const [searching, setSearching] = useState(false);
  const [pulling, setPulling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    setSearching(true);
    setError(null);
    try {
      const res = await fetch(`/api/sam/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `Search failed (${res.status})`);
      setResults(data.results);
      setMock(Boolean(data.mock));
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setResults(null);
    } finally {
      setSearching(false);
    }
  }

  async function pull(r: SamResult) {
    setPulling(r.noticeId);
    setError(null);
    try {
      const res = await fetch(r.attachmentUrl);
      if (!res.ok) throw new Error(`Could not download the attachment (${res.status})`);
      const blob = await res.blob();
      onFile(
        new File([blob], `${r.solicitationNumber}.pdf`, { type: "application/pdf" })
      );
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setPulling(null);
    }
  }

  return (
    <div className="border border-[#d7dee6] bg-white p-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !searching && void search()}
          placeholder="Search live SAM.gov solicitations — keyword or title"
          className="flex-1 border border-[#d7dee6] px-3 py-2 text-sm text-[#16324f] placeholder-[#51606f]/70 focus:border-[#16324f] focus:outline-none"
        />
        <button
          onClick={() => void search()}
          disabled={searching || disabled}
          className="bg-[#16324f] px-4 py-2 text-sm text-white hover:bg-[#0f2438] disabled:opacity-50"
        >
          {searching ? "Searching…" : "Search SAM.gov"}
        </button>
      </div>
      <p className="mt-2 text-xs text-[#51606f]">
        Shared team key, ~10 requests/day — searches are cached for the day.
      </p>

      {mock && (
        <p className="mt-2 border border-[#d7dee6] bg-[#f5f7f9] px-3 py-2 text-xs text-[#51606f]">
          SAM_API_KEY isn&apos;t set — showing sample results so the flow still works.
        </p>
      )}
      {error && (
        <p className="mt-2 border border-[#9a6a1e]/40 bg-[#9a6a1e]/5 px-3 py-2 text-xs text-[#9a6a1e]" role="alert">
          {error}
        </p>
      )}

      {results && results.length === 0 && (
        <p className="mt-3 text-sm text-[#51606f]">
          No solicitations with attachments matched. Try a broader keyword.
        </p>
      )}
      {results && results.length > 0 && (
        <ul className="mt-3 divide-y divide-[#d7dee6] border border-[#d7dee6]">
          {results.map((r) => (
            <li key={r.noticeId} className="flex items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm text-[#16324f]">{r.title}</p>
                <p className="text-xs text-[#51606f]">
                  {r.solicitationNumber}
                  {r.postedDate && <> · posted {r.postedDate}</>}
                </p>
              </div>
              <button
                onClick={() => void pull(r)}
                disabled={pulling !== null || disabled}
                className="shrink-0 border border-[#16324f] px-3 py-1 text-xs text-[#16324f] hover:bg-[#16324f] hover:text-white disabled:opacity-50"
              >
                {pulling === r.noticeId ? "Pulling…" : "Pull into app"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

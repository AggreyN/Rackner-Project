"use client";

// Home — search-first landing (build plan §1 step 3). A search bar over
// live SAM.gov opportunities up top; below it, suggested contracts ranked
// against the lifecycle plan. No upload flow, no role picker — the pivot
// leads with discovery.

import { useCallback, useEffect, useState } from "react";
import TopBar from "@/components/TopBar";
import OpportunityCard from "@/components/OpportunityCard";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getProfile, getSuggested, searchOpportunities } from "@/lib/api";
import type { OpportunitySummary, Profile } from "@/lib/types";

export default function Home() {
  const { ready, email } = useRequireAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<OpportunitySummary[] | null>(null);
  const [suggested, setSuggested] = useState<OpportunitySummary[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = useCallback(() => {
    if (email) getProfile(email).then(setProfile).catch(() => {});
  }, [email]);

  const loadSuggested = useCallback(() => {
    getSuggested()
      .then(setSuggested)
      .catch(() => setSuggested([]));
  }, []);

  useEffect(() => {
    if (!ready) return;
    loadProfile();
    loadSuggested();
  }, [ready, loadProfile, loadSuggested]);

  async function handleSearch(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);
    setBusy(true);
    try {
      setResults(await searchOpportunities(query));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResults(null);
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return <main className="min-h-screen bg-[#f5f7f9]" />;

  const showingSearch = results !== null;

  return (
    <main className="min-h-screen bg-[#f5f7f9]">
      <TopBar
        profile={profile}
        onLifecycleUpdated={() => {
          setSuggested(null); // show the skeleton while re-ranking
          loadProfile();
          loadSuggested();
        }}
      />

      <div className="mx-auto max-w-5xl px-4 pb-16 pt-8 sm:px-6">
        <h2 className="text-2xl font-semibold text-[#16324f]">Find your next opportunity</h2>
        <p className="mt-0.5 text-sm text-[#51606f]">
          Search live SAM.gov solicitations, or ask the assistant on any opportunity.
        </p>

        <form onSubmit={handleSearch} className="mt-4 flex flex-col gap-2.5 sm:flex-row">
          <div className="flex flex-1 items-center gap-2.5 rounded-lg border border-[#d7dee6] bg-white px-4 py-3">
            <span className="text-[#51606f]">🔍</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search SAM.gov — keywords, agency, NAICS, set-aside…"
              className="w-full text-[15px] focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-[#16324f] px-6 py-3 text-sm font-semibold text-white hover:bg-[#0f2438] disabled:opacity-60"
          >
            {busy ? "Searching…" : "Search"}
          </button>
        </form>
        <p className="mt-2 text-xs text-[#51606f]">
          💬 Or ask: “What cyber contracts under $10M close in the next 30 days that fit us?”
        </p>

        {error && <p className="mt-4 text-sm text-[#a3231f]">{error}</p>}

        {showingSearch ? (
          <section className="mt-8">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-semibold text-[#16324f]">
                Results{query.trim() ? ` for “${query.trim()}”` : ""}
              </h3>
              <button
                onClick={() => setResults(null)}
                className="text-xs text-[#16324f] underline underline-offset-2 hover:text-[#0f2438]"
              >
                Clear search
              </button>
            </div>
            {results.length === 0 ? (
              <p className="border border-[#d7dee6] bg-white p-6 text-sm text-[#51606f]">
                No live opportunities matched. Try broader keywords or an agency name.
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
                {results.map((o) => (
                  <OpportunityCard key={o.id} opp={o} />
                ))}
              </div>
            )}
          </section>
        ) : (
          <section className="mt-8">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-base font-semibold text-[#16324f]">Suggested for Rackner</h3>
              <span className="text-xs text-[#51606f]">
                {profile?.lifecycle
                  ? "Ranked against your Opportunity Lifecycle plan · updated today"
                  : "Add your lifecycle plan to rank these by fit"}
              </span>
            </div>
            {suggested === null ? (
              <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2" aria-hidden>
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="h-36 animate-pulse border border-[#d7dee6] bg-white" />
                ))}
              </div>
            ) : suggested.length === 0 ? (
              <p className="border border-[#d7dee6] bg-white p-6 text-sm text-[#51606f]">
                Couldn&apos;t load suggestions. Check the backend connection and retry.
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
                {suggested.map((o) => (
                  <OpportunityCard key={o.id} opp={o} />
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}

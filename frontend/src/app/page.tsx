"use client";

// Home — search-first landing (build plan §1 step 3), plus the recompete
// radar. Search runs over live SAM.gov solicitations; the timing filter can
// switch the whole view to EXPIRING AWARDS from USAspending — contracts
// ending in 12–18 months, which is when capture work actually starts.

import { useCallback, useEffect, useState } from "react";
import TopBar from "@/components/TopBar";
import OpportunityCard from "@/components/OpportunityCard";
import TimingFilter from "@/components/TimingFilter";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getProfile, getSuggested, searchOpportunities } from "@/lib/api";
import type {
  OpportunitySummary,
  Profile,
  SearchFilters,
  TimingPreset,
} from "@/lib/types";

export default function Home() {
  const { ready, email } = useRequireAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [query, setQuery] = useState("");
  const [preset, setPreset] = useState<TimingPreset>("all");
  const [filters, setFilters] = useState<SearchFilters>({});
  const [results, setResults] = useState<OpportunitySummary[]>([]);
  const [searchMode, setSearchMode] = useState(false);
  const [suggested, setSuggested] = useState<OpportunitySummary[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = useCallback(() => {
    if (email) getProfile(email).then(setProfile).catch(() => {});
  }, [email]);

  const loadSuggested = useCallback((f: SearchFilters) => {
    getSuggested(f)
      .then(setSuggested)
      .catch(() => setSuggested([]));
  }, []);

  useEffect(() => {
    if (!ready) return;
    loadProfile();
    loadSuggested({});
  }, [ready, loadProfile, loadSuggested]);

  const runSearch = useCallback(async (q: string, f: SearchFilters) => {
    setError(null);
    setSearchMode(true); // switch view first so the skeleton replaces stale cards
    setBusy(true);
    try {
      setResults(await searchOpportunities(q, f));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResults([]);
    } finally {
      setBusy(false);
    }
  }, []);

  // Changing the timing filter re-runs whichever view is showing, so the
  // window applies to search results and suggestions alike.
  function handlePreset(next: TimingPreset, nextFilters: SearchFilters) {
    setPreset(next);
    setFilters(nextFilters);
    if (searchMode || next !== "all") {
      void runSearch(query, nextFilters);
    } else {
      setSuggested(null);
      loadSuggested(nextFilters);
    }
  }

  if (!ready) return <main className="min-h-screen bg-[#f5f7f9]" />;

  const showingSearch = searchMode;

  return (
    <main className="min-h-screen bg-[#f5f7f9]">
      <TopBar
        profile={profile}
        onLifecycleUpdated={() => {
          setSuggested(null); // show the skeleton while re-ranking
          loadProfile();
          loadSuggested(filters);
        }}
      />

      <div className="mx-auto max-w-5xl px-4 pb-16 pt-8 sm:px-6">
        <h2 className="text-2xl font-semibold text-[#16324f]">Find your next opportunity</h2>
        <p className="mt-0.5 text-sm text-[#51606f]">
          Search live SAM.gov solicitations, or work backwards from contracts about to expire.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void runSearch(query, filters);
          }}
          className="mt-4 flex flex-col gap-2.5 sm:flex-row"
        >
          <div className="flex flex-1 items-center gap-2.5 rounded-lg border border-[#d7dee6] bg-white px-4 py-3">
            <span className="text-[#51606f]">🔍</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by keyword, agency, NAICS, set-aside, or incumbent…"
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

        <TimingFilter active={preset} onChange={handlePreset} />

        {error && <p className="mt-4 text-sm text-[#a3231f]">{error}</p>}

        {showingSearch ? (
          <section className="mt-8" data-testid="results" data-busy={busy}>
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-base font-semibold text-[#16324f]">
                {busy
                  ? "Searching…"
                  : `${results.length} result${results.length === 1 ? "" : "s"}${
                      query.trim() ? ` for “${query.trim()}”` : ""
                    }`}
              </h3>
              <button
                onClick={() => {
                  setSearchMode(false);
                  setResults([]);
                  setPreset("all");
                  setFilters({});
                  setSuggested(null);
                  loadSuggested({});
                }}
                className="shrink-0 text-xs text-[#16324f] underline underline-offset-2 hover:text-[#0f2438]"
              >
                Clear
              </button>
            </div>
            {/* Stale results must not linger under a new filter — swap to
                skeletons so what's on screen always matches the active window. */}
            {busy ? (
              <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2" aria-hidden>
                {[0, 1].map((i) => (
                  <div key={i} className="h-36 animate-pulse border border-[#d7dee6] bg-white" />
                ))}
              </div>
            ) : results.length === 0 ? (
              <p className="border border-[#d7dee6] bg-white p-6 text-sm text-[#51606f]">
                Nothing matched this window. Try widening the timing filter or using broader
                keywords.
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

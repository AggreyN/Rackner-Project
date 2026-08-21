"use client";

// The analysis workspace — the demo's heart. Split pane: compatibility
// score, cited obligations, spend history, contact, and the assistant on
// the left; the source document on the right (collapsible on desktop,
// toggled on mobile). Every claim links back to the source text.

import { use, useEffect, useState } from "react";
import Link from "next/link";
import TopBar from "@/components/TopBar";
import CompatibilityPanel from "@/components/CompatibilityPanel";
import ObligationsPanel, { type CiteTarget } from "@/components/ObligationsPanel";
import SourcePane from "@/components/SourcePane";
import SpendPanel from "@/components/SpendPanel";
import ContactPanel from "@/components/ContactPanel";
import ChatPanel from "@/components/ChatPanel";
import FloatingWindow from "@/components/FloatingWindow";
import BookmarkStar from "@/components/BookmarkStar";
import SavedDrawer from "@/components/SavedDrawer";
import { useChat } from "@/hooks/useChat";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import {
  getAnalysis,
  getContact,
  getOpportunity,
  getProfile,
  getSourceDocument,
  getSpend,
} from "@/lib/api";
import type {
  Analysis,
  ContactResult,
  OpportunitySummary,
  Profile,
  SourceDocument,
  SpendSummary,
} from "@/lib/types";

export default function OpportunityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { ready, email } = useRequireAuth();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [opp, setOpp] = useState<OpportunitySummary | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [doc, setDoc] = useState<SourceDocument | null>(null);
  const [docMissing, setDocMissing] = useState(false); // no RFP posted yet
  const [spend, setSpend] = useState<SpendSummary | null>(null);
  const [contact, setContact] = useState<ContactResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [cite, setCite] = useState<CiteTarget | null>(null);
  const [collapsed, setCollapsed] = useState(false); // desktop right pane
  const [mobilePane, setMobilePane] = useState<"analysis" | "source">("analysis");

  // ONE conversation, two surfaces: the inline panel at the bottom of the
  // analysis column and the floating Anvil window opened from the launcher.
  const chat = useChat(id);
  const [chatOpen, setChatOpen] = useState(false);

  // A cached analysis lands in a couple of seconds. Past that, this is a
  // first-time generation (the backend is reading the whole package, up to
  // ~5 min) — switch to a message that makes the wait look intentional
  // instead of frozen.
  const [firstGeneration, setFirstGeneration] = useState(false);
  useEffect(() => {
    if (analysis || error) return;
    const t = setTimeout(() => setFirstGeneration(true), 4000);
    return () => clearTimeout(t);
  }, [analysis, error]);

  useEffect(() => {
    if (!ready) return;
    if (email) getProfile(email).then(setProfile).catch(() => {});
    getOpportunity(id)
      .then(setOpp)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getAnalysis(id)
      .then(setAnalysis)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getSourceDocument(id)
      .then(setDoc)
      .catch(() => setDocMissing(true));
    getSpend(id).then(setSpend).catch(() => {});
    getContact(id).then(setContact).catch(() => {});
  }, [ready, email, id]);

  function handleCite(target: CiteTarget) {
    setCite(target);
    setCollapsed(false); // desktop: make sure the evidence is visible
    setMobilePane("source"); // mobile: flip to the document
  }

  if (!ready) return <main className="min-h-screen bg-[#f5f7f9]" />;

  const subLine = opp
    ? [
        opp.agency,
        opp.office,
        opp.solicitation_number ? `Solicitation ${opp.solicitation_number}` : null,
        opp.naics ? `NAICS ${opp.naics}` : null,
        opp.set_aside ? `${opp.set_aside} set-aside` : null,
        opp.close_date
          ? `Closes ${new Date(opp.close_date + "T00:00:00").toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";

  return (
    <main className="flex h-screen flex-col bg-[#f5f7f9]">
      <TopBar profile={profile} />

      {/* mobile pane toggle */}
      <div className="flex border-b border-[#d7dee6] bg-white lg:hidden">
        {(["analysis", "source"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setMobilePane(p)}
            className={
              "flex-1 py-2.5 text-center text-xs font-semibold uppercase tracking-widest " +
              (mobilePane === p
                ? "border-b-2 border-[#16324f] text-[#16324f]"
                : "text-[#51606f]")
            }
          >
            {p === "analysis" ? "Analysis" : "Source doc"}
          </button>
        ))}
      </div>

      <div className="flex min-h-0 flex-1">
        {/* LEFT — analysis */}
        <div
          className={
            "min-w-0 overflow-y-auto px-4 py-5 sm:px-6 " +
            (mobilePane === "analysis" ? "block " : "hidden ") +
            "w-full lg:block " +
            (collapsed ? "lg:flex-1" : "lg:w-[52%]")
          }
        >
          <Link
            href="/"
            className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-[#16324f] hover:underline"
          >
            ← Back to search
          </Link>

          {error && (
            <p className="mb-4 border border-[#d7dee6] bg-white p-4 text-sm text-[#a3231f]">
              {error}
            </p>
          )}

          <div className="flex items-start gap-2.5">
            <h1 className="min-w-0 flex-1 text-lg font-semibold leading-snug text-[#16324f]">
              {opp?.title ?? "Loading opportunity…"}
            </h1>
            <BookmarkStar id={id} size="md" />
          </div>
          <p className="mb-4 mt-0.5 text-xs text-[#51606f]">{subLine}</p>

          <div className="space-y-4">
            {analysis ? (
              <>
                <CompatibilityPanel analysis={analysis} onCite={handleCite} />
                {analysis.obligations.length > 0 ? (
                  <ObligationsPanel obligations={analysis.obligations} onCite={handleCite} />
                ) : (
                  <div
                    className="border border-[#d7dee6] bg-white p-4 sm:p-5"
                    data-testid="no-solicitation"
                  >
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
                      Obligations
                    </h3>
                    <p className="text-sm leading-relaxed text-[#51606f]">
                      No solicitation has been posted for this recompete yet, so there is nothing
                      to extract or cite. Fit above is scored from the current award&apos;s scope
                      and its USAspending record.{" "}
                      {opp?.months_to_expiry !== null && opp?.months_to_expiry !== undefined && (
                        <>
                          Expect an RFP roughly{" "}
                          <b className="text-[#16324f]">
                            {Math.max(opp.months_to_expiry - 6, 0)}–{opp.months_to_expiry} months
                          </b>{" "}
                          from now — shape it before then.
                        </>
                      )}
                    </p>
                  </div>
                )}
              </>
            ) : (
              !error && (
                <div className="border border-[#d7dee6] bg-white p-5" data-testid="analysis-loading">
                  <div className="flex items-center gap-3">
                    <div className="h-[64px] w-[64px] animate-pulse rounded-full bg-[#eef2f6]" />
                    <div className="flex-1 space-y-2">
                      <div className="h-3 w-2/3 animate-pulse bg-[#eef2f6]" />
                      <div className="h-3 w-1/2 animate-pulse bg-[#eef2f6]" />
                    </div>
                  </div>
                  {firstGeneration ? (
                    <p className="mt-3 text-xs leading-relaxed text-[#51606f]" data-testid="first-generation">
                      <b className="text-[#16324f]">
                        Reading the full solicitation package — this happens once per opportunity.
                      </b>{" "}
                      Every obligation is extracted and its quote verified against the source
                      before anything is shown. Large packages can take a few minutes; the result
                      is cached for everyone afterward.
                    </p>
                  ) : (
                    <p className="mt-3 text-xs text-[#51606f]">
                      Scoring against your lifecycle plan and extracting cited obligations…
                    </p>
                  )}
                </div>
              )
            )}

            {spend && <SpendPanel spend={spend} />}
            {contact && <ContactPanel contact={contact} />}
            <ChatPanel chat={chat} onCite={handleCite} />
          </div>
        </div>

        {/* RIGHT — source document */}
        <div
          className={
            "min-h-0 min-w-0 flex-1 " +
            (mobilePane === "source" ? "flex " : "hidden ") +
            (collapsed ? "lg:flex lg:flex-none" : "lg:flex")
          }
        >
          <SourcePane
            doc={doc}
            unavailable={docMissing}
            cite={cite}
            collapsed={collapsed}
            onToggle={() => setCollapsed(!collapsed)}
          />
        </div>
      </div>

      {/* Anvil launcher — bottom-left, always reachable without scrolling
          past the obligations. Hidden while the window is open. */}
      {!chatOpen && (
        <button
          onClick={() => setChatOpen(true)}
          data-testid="anvil-launcher"
          aria-label="Open Anvil AI chat"
          className="fixed bottom-5 left-5 z-30 flex h-13 items-center gap-2 rounded-full bg-[#16324f] px-4 py-3 text-sm font-semibold text-white shadow-[0_6px_18px_rgba(22,50,79,.35)] hover:bg-[#0f2438]"
        >
          <span className="text-lg leading-none">💬</span>
          <span className="hidden sm:inline">Ask Anvil</span>
        </button>
      )}

      {chatOpen && (
        <FloatingWindow title="Anvil AI" onClose={() => setChatOpen(false)}>
          <ChatPanel
            chat={chat}
            frameless
            autoFocus
            onCite={(t) => {
              // Citations from the floating window drive the same source-pane
              // highlight; keep the window open so the user can keep asking.
              handleCite(t);
            }}
          />
        </FloatingWindow>
      )}

      <SavedDrawer />
    </main>
  );
}

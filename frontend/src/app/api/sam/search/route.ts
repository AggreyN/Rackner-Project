// SAM.gov opportunity search, proxied server-side so the shared API key
// never reaches the browser. The public key allows ~10 requests/day for the
// whole team, so results are cached per day+query. Without a key we return
// clearly-marked sample results so the intake UI works everywhere.

import { NextRequest, NextResponse } from "next/server";

const SEARCH_URL = "https://api.sam.gov/opportunities/v2/search";

const MOCK_RESULTS = [
  {
    noticeId: "demo-eldp",
    title: "Enterprise Logistics Data Platform (seeded demo)",
    solicitationNumber: "W58RGZ-26-R-0042",
    postedDate: "2026-07-01",
    attachmentUrl: "/samples/TeamAnvil-Demo-Solicitation.pdf",
  },
];

interface Opportunity {
  noticeId?: string;
  title?: string;
  solicitationNumber?: string;
  postedDate?: string;
  resourceLinks?: string[];
}

let cache: { day: string; q: string; results: unknown[] } | null = null;

function fmt(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${mm}/${dd}/${d.getFullYear()}`;
}

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.trim() ?? "";
  const key = process.env.SAM_API_KEY;

  if (!key || key === "your-key-here") {
    return NextResponse.json({ mock: true, results: MOCK_RESULTS });
  }

  const day = new Date().toDateString();
  if (cache && cache.day === day && cache.q === q) {
    return NextResponse.json({ mock: false, cached: true, results: cache.results });
  }

  const today = new Date();
  const monthAgo = new Date();
  monthAgo.setDate(today.getDate() - 30);
  const params = new URLSearchParams({
    api_key: key,
    postedFrom: fmt(monthAgo),
    postedTo: fmt(today),
    limit: "10",
    offset: "0",
    ptype: "o", // solicitations — most likely to carry attachments
  });
  if (q) params.set("title", q);

  const res = await fetch(`${SEARCH_URL}?${params}`);
  if (!res.ok) {
    return NextResponse.json(
      { error: `SAM.gov search failed (${res.status}). The shared key allows ~10 requests/day.` },
      { status: 502 }
    );
  }
  const data = (await res.json()) as { opportunitiesData?: Opportunity[] };
  const results = (data.opportunitiesData ?? [])
    .filter((o) => (o.resourceLinks ?? []).length > 0)
    .map((o) => ({
      noticeId: o.noticeId ?? "",
      title: o.title ?? "Untitled opportunity",
      solicitationNumber: o.solicitationNumber || o.noticeId || "unknown",
      postedDate: o.postedDate ?? "",
      attachmentUrl: `/api/sam/fetch?url=${encodeURIComponent(o.resourceLinks![0])}`,
    }));

  cache = { day, q, results };
  return NextResponse.json({ mock: false, results });
}

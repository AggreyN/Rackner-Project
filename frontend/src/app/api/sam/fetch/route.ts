// Downloads a SAM.gov attachment server-side (the key stays secret) and
// streams it back to the browser. Only https://…sam.gov URLs are allowed —
// this endpoint must not become an open proxy.

import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const raw = req.nextUrl.searchParams.get("url");
  if (!raw) {
    return NextResponse.json({ error: "Missing url parameter" }, { status: 400 });
  }

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return NextResponse.json({ error: "Invalid url" }, { status: 400 });
  }
  const allowed =
    url.protocol === "https:" &&
    (url.hostname === "sam.gov" || url.hostname.endsWith(".sam.gov"));
  if (!allowed) {
    return NextResponse.json(
      { error: "Only https sam.gov attachment URLs are allowed" },
      { status: 400 }
    );
  }

  const key = process.env.SAM_API_KEY;
  if (!key || key === "your-key-here") {
    // No key configured — hand back the seeded demo document instead.
    return NextResponse.redirect(new URL("/samples/TeamAnvil-Demo-Solicitation.pdf", req.url));
  }

  url.searchParams.set("api_key", key);
  const res = await fetch(url);
  if (!res.ok) {
    return NextResponse.json(
      { error: `SAM.gov download failed (${res.status})` },
      { status: 502 }
    );
  }
  return new NextResponse(res.body, {
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/pdf",
      "cache-control": "private, max-age=86400",
    },
  });
}

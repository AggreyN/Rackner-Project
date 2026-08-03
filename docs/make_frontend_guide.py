#!/usr/bin/env python3
"""Generates Rackner-FDI-Frontend-Guide.pdf — the frontend feature inventory
and the frontend<->backend integration guide.

Design matches the app: navy #16324f, white, hairline rules, no gradients.
Regenerate after frontend changes:  python3 docs/make_frontend_guide.py
"""

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#16324f")
NAVY_MUTED = colors.HexColor("#51606f")
LINE = colors.HexColor("#d7dee6")
WASH = colors.HexColor("#f5f7f9")
OK = colors.HexColor("#1e7a46")
WARN = colors.HexColor("#9a6a1e")
BAD = colors.HexColor("#a3231f")

OUT = "docs/Rackner-FDI-Frontend-Guide.pdf"

ss = getSampleStyleSheet()


def style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.5, leading=13.5,
                textColor=colors.HexColor("#1f2933"), alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    "title": style("title", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=NAVY),
    "subtitle": style("subtitle", fontSize=11, leading=15, textColor=NAVY_MUTED),
    "h1": style("h1", fontName="Helvetica-Bold", fontSize=14, leading=18,
                textColor=NAVY, spaceBefore=16, spaceAfter=6),
    "h2": style("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                textColor=NAVY, spaceBefore=10, spaceAfter=3),
    "body": style("body", spaceAfter=5),
    "small": style("small", fontSize=8.5, leading=12, textColor=NAVY_MUTED),
    "cell": style("cell", fontSize=8.5, leading=11.5),
    "thead": style("thead", fontName="Helvetica-Bold", fontSize=8.5, leading=11.5,
                   textColor=colors.white),
    "cellb": style("cellb", fontName="Helvetica-Bold", fontSize=8.5, leading=11.5, textColor=NAVY),
    "code": style("code", fontName="Courier", fontSize=8.5, leading=12,
                  textColor=NAVY, backColor=WASH, borderPadding=6,
                  spaceBefore=4, spaceAfter=8),
    "lead": style("lead", fontSize=10, leading=14.5, spaceAfter=6),
}


def p(text, s="body"):
    return Paragraph(text, S[s])


def bullets(items, s="body"):
    return [Paragraph(f"<bullet>&bull;</bullet> {i}", ParagraphStyle(
        f"b{n}", parent=S[s], leftIndent=12, bulletIndent=2, spaceAfter=3
    )) for n, i in enumerate(items)]


def table(rows, widths, header=True, zebra=True):
    # Header cells must be built with the white style: a TableStyle TEXTCOLOR
    # does NOT override a Paragraph's own colour, so plain cells would render
    # dark-on-navy and vanish.
    data = []
    for r, row in enumerate(rows):
        cells = []
        for c in row:
            if isinstance(c, Paragraph):
                cells.append(c)
            elif header and r == 0:
                cells.append(Paragraph(str(c), S["thead"]))
            else:
                cells.append(p(str(c), "cell"))
        data.append(cells)
    st = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]
    if header:
        st += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ]
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == (0 if header else 1):
                st.append(("BACKGROUND", (0, i), (-1, i), WASH))
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    t.setStyle(TableStyle(st))
    return t


def tag(text, color):
    return Paragraph(
        f'<font color="{color.hexval()}"><b>{text}</b></font>', S["cell"]
    )


# --------------------------------------------------------------- page frame

def decorate(canvas, doc):
    canvas.saveState()
    w, h = LETTER
    # header rule
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, h - 0.62 * inch, w - 0.75 * inch, h - 0.62 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(NAVY_MUTED)
    canvas.drawString(0.75 * inch, h - 0.55 * inch,
                      "Rackner FDI · Frontend Reference & Integration Guide")
    canvas.drawRightString(w - 0.75 * inch, h - 0.55 * inch,
                           "Team Anvil · Remy Tran")
    # footer
    canvas.line(0.75 * inch, 0.62 * inch, w - 0.75 * inch, 0.62 * inch)
    canvas.drawString(0.75 * inch, 0.45 * inch,
                      "Phase 1 · frontend runs standalone against the built-in mock")
    canvas.drawRightString(w - 0.75 * inch, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


doc = BaseDocTemplate(OUT, pagesize=LETTER,
                      leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                      topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                      title="Rackner FDI - Frontend Reference & Integration Guide",
                      author="Remy Tran - Team Anvil")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=decorate)])

F = []  # flowables

# =============================================================== TITLE
F += [
    Spacer(1, 6),
    p("Rackner FDI", "title"),
    p("Federal Document Intelligence — Frontend Reference &amp; Integration Guide", "subtitle"),
    Spacer(1, 10),
    table([
        [p("Owner", "cellb"), p("Remy Tran — Full-Stack &amp; System Design", "cell"),
         p("Stack", "cellb"), p("Next.js 16 · React 19 · TypeScript 5 · Tailwind 4", "cell")],
        [p("Phase", "cellb"), p("Phase 1 — 4-week build, demo end of August", "cell"),
         p("Tests", "cellb"), p("66 Playwright tests · desktop / tablet / mobile", "cell")],
    ], [0.7 * inch, 2.85 * inch, 0.6 * inch, 2.85 * inch], header=False, zebra=False),
    Spacer(1, 12),
    p("What this app does", "h1"),
    p("A capture/BD person searches live federal opportunities, decides fast whether one is worth "
      "pursuing, sees how much money is really behind it, and finds who to talk to. Every AI claim "
      "is cited back to the source text so a human can check it.", "lead"),
    p("The 7/22 reframing replaced the old “upload a contract” flow. Contractors go looking "
      "for contracts — they do not arrive with one in hand. Cut in that pivot: upload-first "
      "intake, role picker, PII pre-upload scan, 3-day retention. Added: sign-in, lifecycle-plan "
      "profile, SAM.gov search, compatibility scoring, spend lookup, contact discovery.", "body"),
    Spacer(1, 4),
    p("The four questions the UI answers", "h2"),
]
F += bullets([
    "<b>What is out there?</b> — SAM.gov search + the recompete radar",
    "<b>Is it worth our time?</b> — compatibility score vs. the Opportunity Lifecycle plan, with cited obligations",
    "<b>How much money is behind it?</b> — USAspending.gov spend history",
    "<b>Who do I talk to?</b> — contact discovery, with Procurement Integrity guardrails",
])

# =============================================================== FEATURES
F += [PageBreak(), p("1 · Feature inventory", "h1"),
      p("Every screen currently implemented, with the component that owns it.", "body")]

F += [p("1.1 · Sign-in — /login", "h2")]
F += [table([
    ["Feature", "Behavior", "Owner file"],
    ["Credential form", "Work email + password, native validation, autoComplete hints.", "app/login/page.tsx"],
    ["Session handling", "JWT stored in sessionStorage; clears on tab close.", "lib/auth.ts"],
    ["Redirect guard", "Already signed in -> bounces to /. No session -> every page bounces here.",
     "hooks/useRequireAuth.ts"],
    ["Error surfacing", "Backend rejection rendered inline under the form.", "app/login/page.tsx"],
    ["Security note", "States hashing + isolated-container posture to the user.", "app/login/page.tsx"],
], [1.25 * inch, 3.6 * inch, 2.15 * inch])]

F += [p("1.2 · Home — /", "h2")]
F += [table([
    ["Feature", "Behavior", "Owner file"],
    ["Search", "Free-text over title, agency, office, NAICS, set-aside, incumbent. Server-side in production.",
     "app/page.tsx"],
    ["<b>Recompete radar</b>", "Timing presets incl. the 12–18 month capture window. Filters are query "
     "params, evaluated server-side.", "components/TimingFilter.tsx"],
    ["Suggested list", "Ranked against the lifecycle plan; falls back to unscored when no plan is on file.",
     "app/page.tsx"],
    ["Opportunity card", "Title, agency line, description, fit badge, timing/value/incumbent meta. "
     "Two variants: solicitation vs expiring award.", "components/OpportunityCard.tsx"],
    ["Fit badge", "0–100 donut-free badge, banded green/amber/red. Shows ‘—’ when unscored.",
     "components/ScoreBadge.tsx"],
    ["Lifecycle plan", "Header chip opens the parsed fit profile; upload/replace the plan PDF.",
     "components/LifecycleModal.tsx"],
    ["App shell", "Brand, plan chip, org, avatar menu with sign-out.", "components/TopBar.tsx"],
    ["States", "Skeletons while loading, empty-result copy, inline errors. Stale results are replaced "
     "by skeletons when the filter changes.", "app/page.tsx"],
], [1.25 * inch, 3.6 * inch, 2.15 * inch])]

F += [PageBreak(), p("1.3 · Opportunity analysis — /opportunity/[id]", "h2"),
      p("The split-pane workspace: analysis on the left, source evidence on the right.", "body")]
F += [table([
    ["Feature", "Behavior", "Owner file"],
    ["Compatibility score", "Donut (0–100) + band, and the 8 weighted CAP factors each scored 1–5 "
     "with a rationale tooltip and a citation link.", "components/CompatibilityPanel.tsx"],
    ["Obligations", "Grouped by time or type. Each shows the plain-English obligation, deadline chip, "
     "verbatim quote, citation, and a verified / not-verified marker.", "components/ObligationsPanel.tsx"],
    ["<b>Click-to-cite</b>", "Clicking a quote, factor citation, or chat citation scrolls the source pane "
     "to that section and highlights the exact sentence.", "components/SourcePane.tsx"],
    ["Source pane", "Parsed sections with headings and page numbers. Collapsible on desktop; a tab on mobile.",
     "components/SourcePane.tsx"],
    ["Spend history", "USAspending bar chart by fiscal year, total obligated, incumbent + UEI, trend.",
     "components/SpendPanel.tsx"],
    ["Contact", "Discovered email with verifier confidence, plus the Procurement Integrity flag when the "
     "solicitation is active.", "components/ContactPanel.tsx"],
    ["Assistant", "Per-opportunity Q&amp;A. Answers carry clickable citations wired to the same highlight path.",
     "components/ChatPanel.tsx"],
    ["Recompete state", "No RFP yet -> obligations and source pane explain why, fit + spend + contact remain.",
     "app/opportunity/[id]/page.tsx"],
], [1.25 * inch, 3.6 * inch, 2.15 * inch])]

F += [p("1.4 · Cross-cutting", "h2")]
F += [table([
    ["Concern", "Implementation"],
    ["Responsive", "Split pane collapses below lg into an Analysis / Source tab toggle. Card grid goes "
     "single-column. Verified on desktop, iPad Mini, iPhone 13."],
    ["Auth", "useRequireAuth guards every page; Bearer token attached to every backend call."],
    ["Design system", "Navy #16324f, white, hairline #d7dee6 borders, wash #f5f7f9. Flat — no gradients, "
     "no glassmorphism. Tokens in lib/theme.ts."],
    ["Offline mode", "With NEXT_PUBLIC_API_URL unset the whole app runs on lib/mock.ts — the demo "
     "fallback if the backend is unavailable."],
], [1.25 * inch, 5.75 * inch])]

# =============================================================== ARCHITECTURE
F += [PageBreak(), p("2 · Architecture", "h1"),
      p("Three layers, one seam. Components never call fetch directly; every backend call goes through "
        "lib/api.ts, and every shape is defined once in lib/types.ts.", "lead")]

F += [Paragraph(
    "frontend/src/<br/>"
    "&nbsp;&nbsp;app/<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;login/page.tsx &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;sign-in<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;page.tsx &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;search + recompete radar + suggestions<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;opportunity/[id]/ &nbsp;&nbsp;the split-pane analysis workspace<br/>"
    "&nbsp;&nbsp;components/ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;11 presentational components<br/>"
    "&nbsp;&nbsp;hooks/ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;useRequireAuth<br/>"
    "&nbsp;&nbsp;lib/<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;types.ts &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;THE LOCKED SCHEMA<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;api.ts &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;THE ONLY FILE THAT TALKS TO THE BACKEND<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;mock.ts &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;in-browser fake backend (demo fallback)<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;auth.ts &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;session token helpers<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;theme.ts &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;design tokens",
    S["code"])]

F += [p("The switch", "h2"),
      p("One environment variable decides whether the app talks to the mock or the real backend. "
        "No component changes either way.", "body"),
      Paragraph("const BASE = process.env.NEXT_PUBLIC_API_URL;<br/>"
                "const USE_MOCK = !BASE;   // unset -&gt; lib/mock.ts, set -&gt; real HTTP",
                S["code"])]

# =============================================================== CONTRACT
F += [PageBreak(), p("3 · The API contract", "h1"),
      p("Ten routes. The backend must return these shapes exactly as defined in lib/types.ts. "
        "All requests except /auth/login carry <b>Authorization: Bearer &lt;token&gt;</b>.", "lead")]

F += [table([
    ["Method + route", "Request", "Response type"],
    ["POST /auth/login", "{ email, password }", "{ access_token }"],
    ["GET /profile", "— (user derived from JWT)", "Profile"],
    ["POST /profile/lifecycle", "multipart: file (PDF)", "LifecycleProfile"],
    ["GET /opportunities/search", "q, kinds, expiring_from, expiring_to", "OpportunitySummary[]"],
    ["GET /opportunities/suggested", "kinds, expiring_from, expiring_to", "OpportunitySummary[]"],
    ["GET /opportunities/{id}", "—", "OpportunitySummary"],
    ["GET /opportunities/{id}/analysis", "—", "Analysis"],
    ["GET /opportunities/{id}/document", "—", "SourceDocument"],
    ["GET /opportunities/{id}/spend", "—", "SpendSummary"],
    ["GET /opportunities/{id}/contact", "—", "ContactResult"],
    ["POST /opportunities/{id}/chat", "{ question }", "ChatAnswer"],
], [2.35 * inch, 2.45 * inch, 2.2 * inch])]

F += [p("Field rules that are easy to get wrong", "h2")]
F += [table([
    ["Rule", "Why it matters"],
    ["<b>verbatim_quote must be an exact substring of the matching SourceSection.text</b>",
     "SourcePane does text.indexOf(quote). Any whitespace or unicode difference and the highlight "
     "silently does nothing — the demo's grounding moment breaks with no error."],
    ["citation.section matches SourceSection.ref after stripping the section sign",
     "“§L.2” must resolve to ref “L.2”, or the scroll target is not found."],
    ["FitFactor.score is 1–5, not 0–100; weight is 0–1 and weights sum to 1",
     "The factor bars render score/5. A 0–100 score would overflow every bar."],
    ["Analysis.band is pursue | conditional | no_bid",
     "Drives the donut color and verdict pill. Thresholds: >= 70 pursue, 50–69 conditional, < 50 no-bid."],
    ["expiry_date / months_to_expiry / current_award_value are non-null ONLY for kind = expiring_award",
     "The card switches to the recompete layout on these fields. Non-null on a solicitation renders "
     "the wrong variant."],
    ["Unverified quotes must arrive with verified = false, not be dropped",
     "The UI flags them. Silently dropping them hides a hallucination instead of surfacing it."],
], [2.55 * inch, 4.45 * inch])]

# =============================================================== INTEGRATION
F += [PageBreak(), p("4 · Integrating frontend and backend", "h1")]

F += [p("Step 1 — point the frontend at the backend", "h2"),
      Paragraph("# frontend/.env  (git-ignored)<br/>"
                "NEXT_PUBLIC_API_URL=http://localhost:8000<br/><br/>"
                "# then<br/>"
                "npm run dev", S["code"]),
      p("Leave it unset to run on the mock. That is also the demo-day rollback: unset the variable, "
        "redeploy, and the full UI still works.", "small")]

F += [p("Step 2 — backend prerequisites", "h2")]
F += [table([
    ["Requirement", "Detail"],
    ["CORS", "Allow the frontend origin (localhost:3000 in dev, the deployed host in production). "
     "This is the first thing that breaks."],
    ["Auth header", "Accept Authorization: Bearer &lt;jwt&gt;. Login response field must be named "
     "access_token."],
    ["HTTPS", "Required in production. Mixed content is blocked by the browser."],
    ["Content type", "application/json on every route except /profile/lifecycle (multipart)."],
], [1.25 * inch, 5.75 * inch])]

F += [p("Step 3 — verify in this order", "h2"),
      p("Each step exercises one more layer. Stop at the first failure.", "small")]
F += [table([
    ["#", "Check", "Confirms"],
    ["1", "Sign in with a real account", "CORS, TLS, auth, token storage"],
    ["2", "Header chip shows the lifecycle plan", "GET /profile + JWT round-trip"],
    ["3", "Suggested list renders with fit badges", "Scoring joined to the opportunity list"],
    ["4", "Search returns filtered results", "SAM.gov integration + server-side query"],
    ["5", "Open an opportunity; donut and factors render", "Analysis shape, 1–5 scores, band"],
    ["6", "Click an obligation quote; source highlights", "<b>Citation grounding — the demo moment</b>"],
    ["7", "Spend chart and contact card render", "USAspending + email discovery"],
    ["8", "Ask the assistant a question", "LLM round-trip + citation links"],
], [0.35 * inch, 3.5 * inch, 3.15 * inch])]

F += [PageBreak(), p("5 · Known gaps and risks", "h1"),
      p("Honest list as of this build. Ranked by how likely each is to bite during integration.", "lead")]

F += [table([
    ["Risk", "Detail", "Owner"],
    [tag("HIGH", BAD), p("<b>LLM latency.</b> The mock answers in ~1s; a real gov-safe LLM reading a "
                         "100-page solicitation may take 30s or more. The client sets no fetch timeout, "
                         "so a slow analysis shows the skeleton forever with no cancel. Needs either a "
                         "202 + poll endpoint or streaming — a contract change, so decide before "
                         "integration week.", "cell"), p("Remy + Aggrey", "cell")],
    [tag("HIGH", BAD), p("<b>Quote matching.</b> Highlighting is an exact substring match. Any "
                         "normalization difference between the extractor and the analysis output "
                         "silently disables the demo's grounding moment.", "cell"), p("Aggrey + Kaliza", "cell")],
    [tag("MED", WARN), p("<b>Raw error text reaches users.</b> The client throws "
                         "`${status}: ${body}`, and the login page renders it directly — a failed "
                         "login can display raw JSON. Needs an error-mapping layer.", "cell"), p("Remy", "cell")],
    [tag("MED", WARN), p("<b>Silent secondary failures.</b> Spend and contact use empty catch handlers; "
                         "if those endpoints 500, the panels just do not appear, with no message.",
                         "cell"), p("Remy", "cell")],
    [tag("GAP", NAVY_MUTED), p("<b>Recompete radar has no backend.</b> kinds=expiring_award with an "
                               "expiry window needs a USAspending award index queryable by "
                               "period-of-performance end date. Not in the current build plan.",
                               "cell"), p("Aggrey", "cell")],
    [tag("GAP", NAVY_MUTED), p("<b>Chat sends no history.</b> askChat(id, question) has no prior turns, "
                               "so follow-up questions will not work. Adding history changes the "
                               "contract.", "cell"), p("Remy + Kaliza", "cell")],
    [tag("GAP", NAVY_MUTED), p("<b>Deploy target unresolved.</b> amplify.yml and the CI workflow still "
                               "target Amplify, but the 7/22 meeting chose ECS/EC2. Blocks Week 1 "
                               "containerization and Week 4 deploy.", "cell"), p("Remy", "cell")],
], [0.6 * inch, 4.75 * inch, 1.65 * inch])]

F += [p("Everything data-shaped is still mock", "h2"),
      p("To be explicit for any reviewer: the loop, the rendering, and the interactions are real, but "
        "every value on screen today comes from lib/mock.ts. There is no live SAM.gov call, no "
        "USAspending call, and no LLM in the frontend. That is the seam working as designed — "
        "the data source swaps without the UI knowing.", "body")]

doc.build(F)
print(f"wrote {OUT}")

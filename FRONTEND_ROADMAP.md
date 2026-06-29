# Remy — Role 3 (Full Stack & Infrastructure Lead) Build Roadmap

**Project:** Rackner AI Innovation Fellowship — Contract Obligation Extractor
**Your job in one sentence:** build the web app people actually see and touch — the split-pane where a contract PDF sits next to its extracted obligations — plus the SAM.gov data pipeline and the deployment that keeps it all live. **You own the demo wow-moment: click an obligation, watch it highlight in the contract.**
**Repo:** https://github.com/AggreyN/Rackner-Project (same repo as Aggrey — your code lives in a `frontend/` folder)

---

## Two strategic decisions that shape your whole build order

Read these first — they're the difference between a smooth summer and a panicked Demo Day.

### 1. Infrastructure FIRST, not last
Most teams build features for 11 weeks and try to deploy the weekend before Demo Day — then everything breaks. You will do the opposite: **get a live, auto-deploying URL in Week 1**, while it's a "hello world." Every push after that just updates the live site. Deployment becomes a non-event instead of a crisis.

### 2. Build against MOCK data until the real API exists
Aggrey's real backend API isn't ready until **Week 8**. If you wait for it, you lose half the summer. Instead: in Week 3, you, Aggrey, and Role 1 agree on the **shared "obligation" JSON shape** (one document everyone codes to). Then you build your entire UI against a fake `mock-obligations.json` file in that exact shape. When Aggrey's real API lands in Week 8, you swap the data source and everything just works. **This one decision lets all three of you build in parallel instead of waiting on each other.**

---

## What to code first (the order, and why)

| Order | What | Why it's in this slot |
|---|---|---|
| 1 | **Deploy pipeline + app scaffold** | Nothing else matters if you can't ship it. Do it while it's trivial. |
| 2 | **SAM.gov integration** | Produces the real demo PDFs the *whole team* needs — unblocks Aggrey's testing immediately. |
| 3 | **Agree the shared JSON contract + build a mock** | Lets you build the UI without waiting for the backend. |
| 4 | **In-browser PDF viewer** | The left half of the product; everything visual builds on it. |
| 5 | **Split-pane + obligation list** | The core layout users interact with. |
| 6 | **Click-to-highlight** | The demo centerpiece — needs the viewer + list to exist first. |
| 7 | **Swap mock → real API** | Only possible once Aggrey ships endpoints (Week 8). |
| 8 | **Polish, export, deploy hardening** | Last, once it works end-to-end. |

---

## Week-by-week (matches your calendar deadlines)

**Wk1 · Jul 3 — Foundation + live deploy pipeline**
Scaffold a Next.js + TypeScript app in `frontend/`, add Tailwind CSS, and deploy it to Render or Railway with **auto-deploy on every push**. A "hello world" should be reachable at a public URL, and CI should run lint/build on pull requests.
*Coordinate:* agree repo layout with Aggrey — his backend is in `ingestion/ db/ api/`; your app goes in `frontend/`.

**Wk2 · Jul 10 — SAM.gov integration**
Call the SAM.gov "Get Opportunities" API, list opportunities, and download their attachment PDFs. Save 3–5 real solicitations into `data/samples/`.
*Coordinate:* hand those PDFs to Aggrey this week — they unblock his ingestion testing.

**Wk3 · Jul 17 — Design + app shell + the JSON contract**
Wireframe the split-pane in Figma. Build the app shell (nav, layout, routing) and a document-list page rendering **mock** data.
*Coordinate:* with Role 1 + Aggrey, lock the shared obligation JSON shape and save a `mock-obligations.json` you'll all code against.

**Wk4 · Jul 24 — In-browser PDF viewer**
Render a PDF in the browser using `react-pdf` / PDF.js, with page navigation. Load a file from `data/samples/`.

**Wk5 · Jul 31 — Split-pane wired to mock obligations**
PDF on the left, obligation list on the right, reading your `mock-obligations.json`. Make the split responsive.

**Wk6 · Aug 7 — Obligation list UI**
Render obligations with type, deadline, and status badges; add sort/filter; handle empty and loading states. Still mock data.

**Wk7 · Aug 14 — The wow-moment: click-to-highlight**
Click an obligation → scroll to and highlight its exact source span in the PDF, using the page + coordinates in the schema. This is what sells the product on Demo Day.
*Coordinate:* confirm the coordinate format with Aggrey (his Week 7 citation-grounding output: page + char/bbox).

**Wk8 · Aug 21 — Swap mock → real API**
Integrate Aggrey's FastAPI endpoints: upload a PDF → fetch real obligations → render. Wire the accept/edit/reject review actions.
*Coordinate:* agree request/response shapes with Aggrey early in the week.

**Wk9 · Aug 28 — Review workflow + states**
Edit an obligation, change its status, and persist via the API. Add solid loading/empty/error states and optimistic UI.

**Wk10 · Sep 4 — Polish, export, responsiveness, accessibility**
CSV/print export button, a styling pass, mobile-friendly layout, and accessibility basics (keyboard nav, screen-reader labels).

**Wk11 · Sep 11 — Deploy hardening + demo prep**
Production deploy stable with environment variables/secrets handled properly. Run on the 10–15 demo docs, do a full-team dry run, and have a rollback plan.

**Wk12 · Sep 18 — 🚀 Demo Day**
You drive the live demo. The click-to-highlight moment is yours — practice it until it's flawless.

---

## Udemy courses for your role

Buy these on sale (~$13–18 — Udemy runs sales constantly; never pay full price). You won't finish them cover-to-cover — use them to get unstuck, in this priority:

**Start here (React + Next.js — your core):**
- **React – The Complete Guide (incl. Next.js, Redux)** — Maximilian Schwarzmüller. The most popular React course; covers Next.js too: https://www.udemy.com/course/react-the-complete-guide-incl-redux/
- **The Ultimate React Course 2025: React, Next.js, Redux & More** — Jonas Schmedtmann. Excellent modern alternative if you prefer his teaching style: https://www.udemy.com/course/the-ultimate-react-course/

**Next.js in depth (your framework):**
- **Next.js & React – The Complete Guide** — Maximilian Schwarzmüller: https://www.udemy.com/course/nextjs-react-the-complete-guide/

**TypeScript (you're using it from Week 1):**
- **React & TypeScript – The Practical Guide** — pairs TS directly with React, exactly your use case: https://www.udemy.com/course/react-typescript-the-practical-guide/

**Styling (Tailwind CSS):**
- **Tailwind CSS From Scratch | Learn By Building Projects** — Brad Traversy: https://www.udemy.com/course/tailwind-from-scratch/
- Browse Udemy's Tailwind topic for current top-rated picks: https://www.udemy.com/topic/tailwind-css/

**Free references you'll use constantly (don't buy these — they're the official docs):**
- Next.js Learn (interactive official course): https://nextjs.org/learn
- React official docs (the new ones are excellent): https://react.dev/learn
- TypeScript handbook: https://www.typescriptlang.org/docs/handbook/intro.html
- Tailwind docs: https://tailwindcss.com/docs
- react-pdf (your PDF viewer, Week 4): https://github.com/wojtekmaj/react-pdf
- Render deploy docs: https://render.com/docs · Railway: https://docs.railway.app/
- SAM.gov Get Opportunities API (Week 2): https://open.gsa.gov/api/get-opportunities-public-api/

---

## How you fit with the team

- **Role 1 (AI & Product):** defines the obligation JSON shape you render. Agree it in Week 3.
- **Role 2 (Aggrey · Data & Backend):** ships the API you call in Week 8, and the citation coordinates that power your Week 7 highlight. You feed *him* SAM.gov PDFs in Week 2.
- **You (Role 3):** the face of the product and the thing that's actually live. When your deploy is solid and the highlight works, the whole demo lands.

*Mantra: ship something live in Week 1, build against mocks so you never wait, and make the highlight moment unforgettable.*

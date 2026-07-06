/**
 * Pull a few real solicitations from SAM.gov and save their PDF attachments
 * into  ../data/samples  so the whole team has demo documents to work with.
 *
 * Run it from the frontend/ folder:   npm run samples
 * Requires  SAM_API_KEY  in  frontend/.env   (see .env.example)
 *
 * IMPORTANT: the public API key allows only ~10 requests/day, SHARED across the
 * team. This script is deliberately frugal:
 *   - it caches the search result for the day (re-runs cost 0 search requests)
 *   - it skips PDFs already on disk (no re-downloading)
 *   - it stops after a small number of PDFs
 * Run it only when you actually need fresh documents.
 */
import { writeFile, mkdir, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";

// --- 1. Load the secret API key from .env (never hard-code secrets) ----------
try {
  process.loadEnvFile(".env");
} catch {
  // No .env file found — we'll fall back to an already-set env variable.
}

function requireApiKey(): string {
  const key = process.env.SAM_API_KEY;
  if (!key || key === "your-key-here") {
    console.error("[error] Missing SAM_API_KEY. Add it to frontend/.env (see .env.example).");
    process.exit(1);
  }
  return key; // TypeScript now knows this is definitely a string
}

const API_KEY = requireApiKey();

// --- 2. Config ---------------------------------------------------------------
const SEARCH_URL = "https://api.sam.gov/opportunities/v2/search";
const OUTPUT_DIR = join("..", "data", "samples"); // -> repo-root/data/samples
const CACHE_FILE = join(OUTPUT_DIR, "_search-cache.json");
const HOW_MANY_PDFS = 3; // keep small — every download costs a shared request

// Count every real API request so we can report usage against the 10/day limit.
let requestsUsed = 0;

// Minimal shape of the bits of the SAM.gov response we actually use.
type Opportunity = {
  resourceLinks?: string[];
  solicitationNumber?: string;
  noticeId?: string;
  title?: string;
};
type SearchResponse = {
  opportunitiesData?: Opportunity[];
};

// SAM.gov wants dates as MM/dd/yyyy, and the window must be <= 1 year.
function formatDate(date: Date): string {
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${mm}/${dd}/${date.getFullYear()}`;
}

// Append the api_key to a download URL (handles URLs that already have a "?").
function withKey(url: string): string {
  return url.includes("?") ? `${url}&api_key=${API_KEY}` : `${url}?api_key=${API_KEY}`;
}

// Return today's cached search results if we already searched today; else null.
async function readTodaysCache(): Promise<SearchResponse | null> {
  if (!existsSync(CACHE_FILE)) return null;
  try {
    const cached = JSON.parse(await readFile(CACHE_FILE, "utf8")) as {
      fetchedOn?: string;
      response?: SearchResponse;
    };
    if (cached.fetchedOn === new Date().toDateString()) return cached.response ?? null;
  } catch {
    // corrupt/old cache — ignore and re-search
  }
  return null;
}

// --- 3. Search (cached) ------------------------------------------------------
async function search(): Promise<SearchResponse> {
  const cached = await readTodaysCache();
  if (cached) {
    console.log("[ok] Using today's cached search (0 API requests spent).");
    return cached;
  }

  const today = new Date();
  const monthAgo = new Date();
  monthAgo.setDate(today.getDate() - 30);

  const params = new URLSearchParams({
    api_key: API_KEY,
    postedFrom: formatDate(monthAgo),
    postedTo: formatDate(today),
    limit: "50",
    offset: "0",
    ptype: "o", // "o" = Solicitation — most likely to carry attachments
  });

  console.log("Searching SAM.gov opportunities (last 30 days)... [1 request]");
  const res = await fetch(`${SEARCH_URL}?${params}`);
  requestsUsed++;
  if (!res.ok) {
    console.error(`[error] Search failed: ${res.status} ${res.statusText}`);
    console.error(await res.text());
    process.exit(1);
  }

  const response = (await res.json()) as SearchResponse;
  await mkdir(OUTPUT_DIR, { recursive: true });
  await writeFile(CACHE_FILE, JSON.stringify({ fetchedOn: today.toDateString(), response }));
  return response;
}

// --- 4. Main -----------------------------------------------------------------
async function main() {
  const data = await search();
  const opportunities: Opportunity[] = data.opportunitiesData ?? [];
  console.log(`   Found ${opportunities.length} opportunities.`);

  await mkdir(OUTPUT_DIR, { recursive: true });

  let saved = 0;
  for (const opp of opportunities) {
    if (saved >= HOW_MANY_PDFS) break;

    const links: string[] = opp.resourceLinks ?? [];
    if (links.length === 0) continue; // this opportunity has no attachments

    const name = String(opp.solicitationNumber || opp.noticeId || `sample-${saved}`)
      .replace(/[^a-zA-Z0-9-_]/g, "_");
    const filePath = join(OUTPUT_DIR, `${name}.pdf`);

    // Frugal: never re-download a PDF we already have.
    if (existsSync(filePath)) {
      console.log(`[skip] Already have ${filePath} (0 requests).`);
      saved++;
      continue;
    }

    try {
      const fileRes = await fetch(withKey(links[0])); // grab its first attachment
      requestsUsed++;
      if (!fileRes.ok) {
        console.warn(`[warn] Skipped a link (${fileRes.status})`);
        continue;
      }
      const buffer = Buffer.from(await fileRes.arrayBuffer());

      // Keep only real PDFs (check the header or the file's magic bytes).
      const looksPdf =
        fileRes.headers.get("content-type")?.includes("pdf") ||
        buffer.subarray(0, 4).toString() === "%PDF";
      if (!looksPdf) continue;

      await writeFile(filePath, buffer);
      saved++;
      console.log(`[ok] Saved ${filePath}  (${opp.title ?? "untitled"})`);
    } catch (err) {
      console.warn(`[warn] Error downloading: ${(err as Error).message}`);
    }
  }

  console.log(`\nDone. Saved/kept ${saved} PDF(s) in ${OUTPUT_DIR}.`);
  console.log(`API requests spent this run: ${requestsUsed} (shared daily limit is ~10).`);
  if (saved === 0) {
    console.log("[warn] No PDFs this time — try a wider date range or remove the ptype filter.");
  }
}

main();

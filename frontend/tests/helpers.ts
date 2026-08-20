import { expect, type Page, type TestInfo } from "@playwright/test";

// Seed a signed-in session before any page script runs — the mock backend
// issues tokens shaped like this, and useRequireAuth only checks presence.
export async function signIn(page: Page, email = "remy@rackner.com"): Promise<void> {
  await page.addInitScript(
    ([e]) => {
      sessionStorage.setItem("fdi_token", `mock-jwt-${btoa(e)}`);
      sessionStorage.setItem("fdi_email", e);
    },
    [email]
  );
}

/** The split pane goes side-by-side at Tailwind's lg breakpoint (1024px).
 *  Below that (tablet portrait + mobile) the workspace uses the pane toggle. */
export function isDesktop(testInfo: TestInfo): boolean {
  return testInfo.project.name === "desktop";
}

/** Pick a timing preset and wait for the results that belong to it.
 *
 *  The home page is URL-driven: a preset click is a router.push, so the
 *  PREVIOUS result set is still on screen — and still data-busy="false" —
 *  for a beat afterwards. Waiting on the URL first, then on the busy flag,
 *  is what makes this deterministic; asserting on cards without it reads
 *  whatever the last query returned.
 */
export async function selectTiming(
  page: Page,
  preset: "all" | "recompete" | "expiring_soon" | "open"
): Promise<void> {
  await page.getByTestId(`timing-${preset}`).click();
  if (preset === "all") {
    await page.waitForURL((url) => !url.searchParams.has("timing"));
  } else {
    await page.waitForURL((url) => url.searchParams.get("timing") === preset);
  }
  await expect(page.getByTestId("results")).toHaveAttribute("data-busy", "false");
}

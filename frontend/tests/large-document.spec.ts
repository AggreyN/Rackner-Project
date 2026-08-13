import { test, expect, type Page } from "@playwright/test";

// Big-package rendering, matched to app/services/ingest.py::split_sections.
// Sections are unbounded heading-to-heading slices, so the pane has to stay
// smooth for BOTH shapes: many-small (PCTE, 107 sections) and few-huge
// (4 sections, >40K chars). Includes the performance budgets that stand in
// for testing on the demo laptop — if a change makes rendering heavy again,
// these fail in CI rather than on stage.

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("remy@rackner.com");
  await page.getByLabel("Password").fill("demo-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Find your next opportunity" })).toBeVisible();
}

async function open(page: Page, card: string, isMobile: boolean | undefined) {
  await signIn(page);
  await page.getByTestId("opportunity-card").filter({ hasText: card }).click();
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 20_000 });
  if (isMobile) await page.getByRole("button", { name: "Source doc" }).click();
  await expect(page.getByTestId("source-toc")).toBeVisible();
}

test("many-small package: TOC covers every section, none rendered by default", async ({
  page,
  isMobile,
}) => {
  await open(page, "PCTE", isMobile);
  const count = await page.getByTestId("section-toggle").count();
  expect(count).toBeGreaterThan(100);
  await expect(page.getByTestId("toc-entry")).toHaveCount(count);
  await expect(page.getByTestId("section-body")).toHaveCount(0);
});

test("few-huge package also gets large mode (character threshold, not count)", async ({
  page,
  isMobile,
}) => {
  // Only 4 sections — a count-only threshold would render >100K chars naively.
  await open(page, "Cloud Migration", isMobile);
  await expect(page.getByTestId("toc-entry")).toHaveCount(4);
  await expect(page.getByTestId("section-body")).toHaveCount(0);
});

test("deduped clause refs are distinct, navigable entries", async ({ page, isMobile }) => {
  await open(page, "PCTE", isMobile);
  // The backend emits 52.212-4, "52.212-4 #2", "52.212-4 #3".
  for (const ref of ["52.212-4", "52.212-4 #2", "52.212-4 #3"]) {
    await expect(
      page.getByTestId("toc-entry").filter({ hasText: new RegExp(`^${ref.replace(".", "\\.")}$`) })
    ).toHaveCount(1);
  }
  await page.getByTestId("toc-entry").filter({ hasText: /^52\.212-4 #2$/ }).click();
  await expect(page.getByTestId("section-body")).toHaveCount(1);
  await expect(page.getByTestId("section-body")).toContainText("alternate I terms");
});

test("page-fallback refs (pN) render", async ({ page, isMobile }) => {
  await open(page, "PCTE", isMobile);
  await expect(page.getByTestId("toc-entry").filter({ hasText: /^p101$/ })).toHaveCount(1);
});

test("very long sections clamp, with a way to see the rest", async ({ page, isMobile }) => {
  await open(page, "PCTE", isMobile);
  // Section C is the enormous PWS slice.
  await page.getByTestId("toc-entry").filter({ hasText: /^C$/ }).click();
  const showFull = page.getByTestId("show-full-section");
  await expect(showFull).toBeVisible();
  const clampedLen = (await page.getByTestId("section-body").innerText()).length;
  expect(clampedLen).toBeLessThan(6_000); // bounded regardless of source size

  await showFull.click();
  await expect(page.getByTestId("show-full-section")).toHaveCount(0);
  const fullLen = (await page.getByTestId("section-body").innerText()).length;
  expect(fullLen).toBeGreaterThan(clampedLen * 3);
});

test("citing inside a huge section still highlights (never clipped by the clamp)", async ({
  page,
}) => {
  await signIn(page);
  await page.getByTestId("opportunity-card").filter({ hasText: "PCTE" }).click();
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 20_000 });

  await page
    .getByTitle("View in the source document")
    .filter({ hasText: "99.5 percent availability" })
    .click();
  await expect(page.getByTestId("cite-highlight")).toBeVisible();
  await expect(page.getByTestId("cite-highlight")).toContainText("99.5 percent availability");
});

// --- performance budgets (stand-in for the demo laptop) ---------------------

test("collapsed big package stays light in the DOM", async ({ page, isMobile }) => {
  await open(page, "PCTE", isMobile);
  const nodes = await page.evaluate(() => document.querySelectorAll("*").length);
  // ~107 header rows + TOC chips + the analysis pane. Naive rendering of every
  // body was many times this.
  expect(nodes).toBeLessThan(1_500);
});

test("expand-all stays bounded and responsive", async ({ page, isMobile }) => {
  await open(page, "PCTE", isMobile);

  const started = Date.now();
  await page.getByTestId("toggle-all-sections").click();
  await expect(page.getByTestId("section-body").first()).toBeVisible();
  const elapsed = Date.now() - started;

  // The clamp is what makes this safe: every body is capped, so worst-case
  // layout does not scale with source-document size.
  const chars = await page.evaluate(() =>
    Array.from(document.querySelectorAll("[data-testid=section-body]")).reduce(
      (n, el) => n + (el.textContent || "").length,
      0
    )
  );
  expect(chars).toBeLessThan(250_000);
  expect(elapsed).toBeLessThan(5_000);
});

test("scrolling the expanded package does not stall", async ({ page, isMobile }) => {
  await open(page, "PCTE", isMobile);
  await page.getByTestId("toggle-all-sections").click();
  await expect(page.getByTestId("section-body").first()).toBeVisible();

  const pane = page.getByTestId("source-toc").locator("xpath=..");
  const started = Date.now();
  for (let i = 0; i < 12; i++) {
    await pane.evaluate((el) => el.scrollBy(0, 2000));
  }
  expect(Date.now() - started).toBeLessThan(4_000);
});

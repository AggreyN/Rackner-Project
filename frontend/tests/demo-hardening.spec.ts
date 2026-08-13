import { test, expect, type Page } from "@playwright/test";

// Demo-hardening for the 28th: expired-session messaging and
// production-scale document rendering (the 106-section PCTE package).

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("remy@rackner.com");
  await page.getByLabel("Password").fill("demo-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Find your next opportunity" })).toBeVisible();
}

async function openPcte(page: Page) {
  await signIn(page);
  await page.getByTestId("opportunity-card").filter({ hasText: "PCTE" }).click();
  // Analysis + document both loaded.
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 15_000 });
}

test("expired session shows the banner on the login page", async ({ page }) => {
  await page.goto("/login?expired=1");
  await expect(page.getByTestId("session-expired")).toContainText("session expired");
});

test("large package renders a TOC with every section, collapsed by default", async ({
  page,
  isMobile,
}) => {
  await openPcte(page);
  if (isMobile) await page.getByRole("button", { name: "Source doc" }).click();

  await expect(page.getByTestId("source-toc")).toBeVisible();
  await expect(page.getByTestId("toc-entry")).toHaveCount(106);
  await expect(page.getByTestId("section-toggle")).toHaveCount(106);
  // Collapsed by default — no bodies in the DOM, which is what keeps
  // scrolling smooth at 200K characters.
  await expect(page.getByTestId("section-body")).toHaveCount(0);
});

test("TOC jump opens exactly that section", async ({ page, isMobile }) => {
  await openPcte(page);
  if (isMobile) await page.getByRole("button", { name: "Source doc" }).click();

  await page.getByTestId("toc-entry").filter({ hasText: /^M\.6$/ }).click();
  await expect(page.getByTestId("section-body")).toHaveCount(1);
  await expect(page.getByTestId("section-body")).toContainText("CMMC Level 2");
});

test("expand all / collapse all", async ({ page, isMobile }) => {
  await openPcte(page);
  if (isMobile) await page.getByRole("button", { name: "Source doc" }).click();

  await page.getByTestId("toggle-all-sections").click();
  await expect(page.getByTestId("section-body")).toHaveCount(106);
  await page.getByTestId("toggle-all-sections").click();
  await expect(page.getByTestId("section-body")).toHaveCount(0);
});

test("citing an obligation auto-opens the section and highlights the quote", async ({ page }) => {
  await openPcte(page);
  // Click the 99.5%-availability obligation's quote.
  await page
    .getByTitle("View in the source document")
    .filter({ hasText: "99.5 percent availability" })
    .click();
  // The cited section force-opens (even though the doc starts fully
  // collapsed) and the exact sentence glows.
  await expect(page.getByTestId("cite-highlight")).toBeVisible();
  await expect(page.getByTestId("cite-highlight")).toContainText(
    "99.5 percent availability"
  );
});

test("small documents still render fully expanded with no TOC", async ({ page, isMobile }) => {
  await signIn(page);
  await page.getByTestId("opportunity-card").filter({ hasText: "Managed Cybersecurity" }).click();
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 15_000 });
  if (isMobile) await page.getByRole("button", { name: "Source doc" }).click();

  await expect(page.getByTestId("source-toc")).toHaveCount(0);
  await expect(page.getByTestId("section-toggle")).toHaveCount(0);
  // All five DISA sections are open without any interaction.
  await expect(page.getByTestId("section-body")).toHaveCount(5);
});

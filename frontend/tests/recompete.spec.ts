import { test, expect, type Page } from "@playwright/test";

// The recompete radar: find contracts expiring 12–18 months out, which is
// when capture work can still shape the requirement.

/** Filter changes are async; wait for the settled result set rather than
 *  racing the in-flight request and reading stale cards. */
async function settled(page: Page) {
  await expect(page.getByTestId("results")).toHaveAttribute("data-busy", "false");
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("remy@rackner.com");
  await page.getByLabel("Password").fill("demo-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Find your next opportunity" })).toBeVisible();
}

test("recompete window returns only awards expiring in 12-18 months", async ({ page }) => {
  await signIn(page);
  await page.getByTestId("timing-recompete").click();
  await settled(page);

  const cards = page.getByTestId("opportunity-card");
  await expect(cards.first()).toBeVisible();

  // Every result is an expiring award inside the window.
  const count = await cards.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i++) {
    const card = cards.nth(i);
    await expect(card).toHaveAttribute("data-kind", "expiring_award");
    const text = await card.innerText();
    const months = Number(text.match(/Expires in (\d+) months/)?.[1]);
    expect(months).toBeGreaterThanOrEqual(12);
    expect(months).toBeLessThanOrEqual(18);
  }
});

test("the window excludes awards that are too early or too late", async ({ page }) => {
  await signIn(page);

  // ≤24mo includes the 8-month and 22-month awards...
  await page.getByTestId("timing-expiring_soon").click();
  await settled(page);
  const wide = await page.getByTestId("opportunity-card").allInnerTexts();
  expect(wide.join(" ")).toContain("Cyber Range Sustainment"); // 8 months — too late
  expect(wide.join(" ")).toContain("DHS Zero-Trust"); // 22 months — too early

  // ...the 12–18 window drops both.
  await page.getByTestId("timing-recompete").click();
  await settled(page);
  const narrow = await page.getByTestId("opportunity-card").allInnerTexts();
  expect(narrow.join(" ")).not.toContain("Cyber Range Sustainment");
  expect(narrow.join(" ")).not.toContain("DHS Zero-Trust");
});

test("in-window awards are tagged as the capture window", async ({ page }) => {
  await signIn(page);
  await page.getByTestId("timing-recompete").click();
  await settled(page);
  await expect(page.getByTestId("recompete-tag").first()).toHaveText(/Capture window/);
});

test("open solicitations filter excludes expiring awards", async ({ page }) => {
  await signIn(page);
  await page.getByTestId("timing-open").click();
  await settled(page);
  const cards = page.getByTestId("opportunity-card");
  await expect(cards.first()).toBeVisible();
  const count = await cards.count();
  for (let i = 0; i < count; i++) {
    await expect(cards.nth(i)).not.toHaveAttribute("data-kind", "expiring_award");
  }
});

test("a recompete has no obligations but keeps spend and fit", async ({ page }) => {
  await signIn(page);
  await page.getByTestId("timing-recompete").click();
  await settled(page);
  await page.getByTestId("opportunity-card").first().click();

  // Fit is still scored...
  await expect(page.getByTestId("fit-donut")).toBeVisible();
  // ...but there is no RFP to cite yet.
  await expect(page.getByTestId("no-solicitation")).toBeVisible();
  await expect(page.getByTestId("spend-panel")).toBeVisible();
});

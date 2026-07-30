import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

// The search-first landing: SAM.gov search up top, suggested contracts
// ranked against the lifecycle plan below.

test.beforeEach(async ({ page }) => {
  await signIn(page);
  await page.goto("/");
});

test.describe("home", () => {
  test("shows suggested opportunities ranked with fit badges", async ({ page }) => {
    await expect(page.getByText("Suggested for Rackner")).toBeVisible();
    const cards = page.getByTestId("opportunity-card");
    await expect(cards).toHaveCount(4);
    // Ranked: highest fit first (82), lowest last (38)
    await expect(cards.first()).toContainText("Managed Cybersecurity & SOC Support Services");
    await expect(cards.first()).toContainText("82");
    await expect(cards.last()).toContainText("Enterprise IT Help Desk Consolidation");
    await expect(cards.last()).toContainText("38");
  });

  test("lifecycle chip opens the fit profile", async ({ page }) => {
    await page.getByRole("button", { name: "✓ Lifecycle plan on file" }).click();
    await expect(page.getByRole("heading", { name: "Opportunity Lifecycle plan" })).toBeVisible();
    await expect(page.getByText("Rackner-Opportunity-Lifecycle-Plan.pdf")).toBeVisible();
    await expect(page.getByText("Cybersecurity & SOC operations")).toBeVisible();
    await expect(page.getByRole("button", { name: "Replace plan (PDF)" })).toBeVisible();
    await page.getByRole("button", { name: "Close" }).click();
  });

  test("search filters live opportunities and can be cleared", async ({ page }) => {
    await page.getByPlaceholder(/Search SAM\.gov/).fill("devsecops cloud");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByText(/Results for/)).toBeVisible();
    await expect(page.getByTestId("opportunity-card")).toHaveCount(1);
    await expect(page.getByTestId("opportunity-card")).toContainText(
      "Cloud Migration & DevSecOps Engineering"
    );
    await page.getByRole("button", { name: "Clear search" }).click();
    await expect(page.getByText("Suggested for Rackner")).toBeVisible();
    await expect(page.getByTestId("opportunity-card")).toHaveCount(4);
  });

  test("card meta shows closing window, value, and incumbent", async ({ page }) => {
    const card = page.getByTestId("opportunity-card").first();
    await expect(card).toContainText("Closes in 21 days");
    await expect(card).toContainText("Est. $8–12M / 5yr");
    await expect(card).toContainText("Incumbent: SmallCyber LLC");
  });
});

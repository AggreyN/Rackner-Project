import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

// The search-first landing: SAM.gov search up top, suggested contracts
// ranked against the lifecycle plan below.

test.beforeEach(async ({ page }) => {
  await signIn(page);
  await page.goto("/");
});

test.describe("home", () => {
  test("shows suggested opportunities with fit badges", async ({ page }) => {
    await expect(page.getByText("Suggested for Rackner")).toBeVisible();
    const cards = page.getByTestId("opportunity-card");
    // Open solicitations plus the recompete radar's expiring awards.
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThan(4);
    await expect(page.getByText("Managed Cybersecurity & SOC Support Services")).toBeVisible();
    await expect(page.getByText("Enterprise IT Help Desk Consolidation")).toBeVisible();
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
    await page.getByPlaceholder(/Search by keyword/).fill("devsecops");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByTestId("results")).toHaveAttribute("data-busy", "false");
    await expect(page.getByTestId("opportunity-card")).toHaveCount(1);
    await expect(page.getByTestId("opportunity-card")).toContainText(
      "Cloud Migration & DevSecOps Engineering"
    );
    await page.getByRole("button", { name: "Clear" }).click();
    await expect(page.getByText("Suggested for Rackner")).toBeVisible();
  });

  test("card meta shows closing window, value, and incumbent", async ({ page }) => {
    const card = page
      .getByTestId("opportunity-card")
      .filter({ hasText: "Managed Cybersecurity & SOC Support Services" });
    await expect(card).toContainText("Closes in 21 days");
    await expect(card).toContainText("$8–12M / 5yr");
    await expect(card).toContainText("Incumbent: SmallCyber LLC");
  });
});

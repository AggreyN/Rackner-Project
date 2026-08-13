import { test, expect, type Page } from "@playwright/test";

// Demo hardening for the 28th: session expiry and small-document behavior.
// Big-package rendering lives in large-document.spec.ts.

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("remy@rackner.com");
  await page.getByLabel("Password").fill("demo-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Find your next opportunity" })).toBeVisible();
}

test("expired session shows the banner on the login page", async ({ page }) => {
  await page.goto("/login?expired=1");
  await expect(page.getByTestId("session-expired")).toContainText("session expired");
});

test("a normal sign-in shows no expiry banner", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByTestId("session-expired")).toHaveCount(0);
});

test("small documents render fully expanded, with no TOC or toggles", async ({
  page,
  isMobile,
}) => {
  await signIn(page);
  await page.getByTestId("opportunity-card").filter({ hasText: "Managed Cybersecurity" }).click();
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 20_000 });
  if (isMobile) await page.getByRole("button", { name: "Source doc" }).click();

  await expect(page.getByTestId("source-toc")).toHaveCount(0);
  await expect(page.getByTestId("section-toggle")).toHaveCount(0);
  // All five DISA sections are open without any interaction — unchanged
  // behavior for the documents the demo actually walks through.
  await expect(page.getByTestId("section-body")).toHaveCount(5);
});

test("click-to-cite still highlights on a small document", async ({ page }) => {
  await signIn(page);
  await page.getByTestId("opportunity-card").filter({ hasText: "Managed Cybersecurity" }).click();
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 20_000 });

  await page.getByTitle("View in the source document").first().click();
  await expect(page.getByTestId("cite-highlight")).toBeVisible();
});

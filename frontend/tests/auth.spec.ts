import { test, expect } from "@playwright/test";

// The suite runs with the auth flag OFF (demo posture). The full flag-on
// smoke test is a deploy-time checklist item — see docs/DEPLOYMENT.md.

test.describe("auth flag off (demo posture)", () => {
  test("login page explains the flag and links back to the app", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Authentication is switched off")).toBeVisible();
    await page.getByRole("link", { name: "Go to the app" }).click();
    await expect(page).toHaveURL("/");
  });

  test("gated pages stay frictionless — no redirect to /login", async ({ page }) => {
    await page.goto("/workspace/1?role=leadership");
    await expect(page.getByText(/\d+ obligations/)).toBeVisible();
    await expect(page).not.toHaveURL(/login/);
    // and no sign-out affordance when auth is off
    await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
  });
});

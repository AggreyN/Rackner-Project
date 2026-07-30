import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

// Sign-in is step 1 of the FDI flow. The suite runs against the built-in
// mock (no NEXT_PUBLIC_API_URL), which accepts any rackner.com email.

test.describe("auth", () => {
  test("signed-out visit to home redirects to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Rackner FDI" })).toBeVisible();
    await expect(page.getByText("credentials stored as salted hashes")).toBeVisible();
  });

  test("rejects a non-rackner email in mock mode", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill("someone@example.com");
    await page.getByLabel("Password").fill("hunter22");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Use your rackner.com work email")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("signs in with a rackner.com email and lands on search", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill("lauren@rackner.com");
    await page.getByLabel("Password").fill("correct-horse");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Find your next opportunity" })).toBeVisible();
  });

  test("sign out returns to /login", async ({ page }) => {
    await signIn(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Find your next opportunity" })).toBeVisible();
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
});

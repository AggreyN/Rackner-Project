import { test, expect } from "@playwright/test";

// Intake flow: validation → PII scan → confirmation modal → upload →
// processing state → register. All against the built-in mock.

test.describe("upload validation", () => {
  test("rejects non-PDF files with a friendly message", async ({ page }) => {
    await page.goto("/");
    await page.setInputFiles('input[type="file"]', {
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("not a pdf"),
    });
    await expect(page.getByRole("alert").filter({ hasText: /./ }).first()).toContainText("Only PDF files are supported");
  });

  test("rejects oversized files", async ({ page, isMobile }) => {
    test.skip(!!isMobile, "one desktop pass is enough for the 26MB buffer");
    await page.goto("/");
    await page.setInputFiles('input[type="file"]', {
      name: "huge.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.alloc(26 * 1024 * 1024, 1),
    });
    await expect(page.getByRole("alert").filter({ hasText: /./ }).first()).toContainText("the limit is 25 MB");
  });

  test("rejects empty files", async ({ page }) => {
    await page.goto("/");
    await page.setInputFiles('input[type="file"]', {
      name: "empty.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.alloc(0),
    });
    await expect(page.getByRole("alert").filter({ hasText: /./ }).first()).toContainText("empty");
  });
});

test.describe("PII confirmation flow (seeded demo doc)", () => {
  test("cancel keeps the document out; confirm uploads and reaches the register", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Security & Compliance", exact: false }).click();

    // The seeded demo document always trips the PII detector.
    await page.getByRole("button", { name: "Use the seeded demo solicitation" }).click();
    await expect(page.getByText("Sensitive information detected")).toBeVisible();
    await expect(page.getByText("Email address")).toBeVisible();
    await expect(page.getByText("Phone number")).toBeVisible();

    // Cancel: nothing stored, still on the landing page.
    await page.getByRole("button", { name: "Cancel upload" }).click();
    await expect(page.getByText("Sensitive information detected")).toBeHidden();
    await expect(page).toHaveURL("/");

    // Confirm: explicit acknowledgment → upload → workspace.
    await page.getByRole("button", { name: "Use the seeded demo solicitation" }).click();
    await page.getByRole("button", { name: "I understand — upload anyway" }).click();
    await page.waitForURL(/\/workspace\/\d+\?role=security/);

    // Processing state first, then the register.
    await expect(page.getByText("Reading the document…")).toBeVisible();
    await expect(page.getByText(/\d+ obligations/)).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("SAM.gov intake", () => {
  test("search returns results and pulling one enters the intake flow", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Program Management", exact: false }).click();
    await page.getByRole("button", { name: "Search SAM.gov" }).click();
    // Without a key the proxy returns clearly-marked sample results.
    await expect(page.getByText(/SAM_API_KEY isn't set|posted/).first()).toBeVisible();
    await expect(page.getByText("Enterprise Logistics Data Platform", { exact: false }).first()).toBeVisible();
    await page.getByRole("button", { name: "Pull into app" }).first().click();
    // The pulled solicitation goes through the same flow (no PII in its name → straight to upload).
    await page.waitForURL(/\/workspace\/\d+\?role=program/, { timeout: 15_000 });
    await expect(page.getByText(/\d+ obligations/)).toBeVisible({ timeout: 15_000 });
  });
});

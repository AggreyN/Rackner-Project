import { test, expect } from "@playwright/test";

// The suite runs against the built-in mock (no NEXT_PUBLIC_API_URL), so it
// exercises the exact flow the demo uses: land → roles → workspace register.

test.describe("landing", () => {
  test("shows the upload zone and all five role cards", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Drop a federal contract or solicitation PDF here")).toBeVisible();
    for (const label of [
      "Contracts",
      "Proposal & Capture",
      "Program Management",
      "Security & Compliance",
      "Leadership",
    ]) {
      await expect(page.getByRole("button", { name: new RegExp(label) })).toBeVisible();
    }
  });
});

test.describe("workspace register", () => {
  test("renders grouped obligations with evidence", async ({ page }) => {
    await page.goto("/workspace/1?role=security");
    await expect(page.getByText(/\d+ obligations/)).toBeVisible();
    await expect(page.getByText("Immediate (hours)")).toBeVisible();
    await expect(
      page.getByText("Report any cyber incident to DoD", { exact: false })
    ).toBeVisible();
    // evidence: verbatim quote + verified badge + page citation
    await expect(
      page
        .locator("blockquote")
        .filter({ hasText: "The Contractor shall rapidly report cyber incidents" })
    ).toBeVisible();
    await expect(page.getByText("✓ quote verified in source").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /View in document → p\.4/ }).first()).toBeVisible();
  });

  test("role switcher changes the role banner and dimming", async ({ page }) => {
    await page.goto("/workspace/1?role=security");
    await expect(page.getByText("Which clauses apply, and what must we prove?")).toBeVisible();
    await expect(page.getByText(/for your role/)).toBeVisible();
    await page.locator("#role-switcher").selectOption("proposal");
    await expect(
      page.getByText("What do we write, and how will it be evaluated?")
    ).toBeVisible();
  });

  test("group tabs regroup the register", async ({ page }) => {
    await page.goto("/workspace/1?role=contracts");
    await page.getByRole("tab", { name: "By category" }).click();
    await expect(page.getByRole("heading", { name: /security ?\(/i })).toBeVisible();
    await page.getByRole("tab", { name: "By type" }).click();
    await expect(page.getByRole("heading", { name: /reporting ?\(/i })).toBeVisible();
  });

  test("unverified quotes are flagged, never shown as verified", async ({ page }) => {
    await page.goto("/workspace/1?role=contracts");
    await expect(page.getByText("⚠ quote not verified")).toBeVisible();
  });
});

test.describe("split pane", () => {
  test("desktop: document pane collapses and expands", async ({ page, isMobile }) => {
    test.skip(!!isMobile, "collapse is a desktop-only affordance");
    await page.goto("/workspace/1?role=program");
    await expect(page.getByText("Source document")).toBeVisible();
    await page.getByRole("button", { name: "Collapse" }).click();
    await expect(page.getByRole("button", { name: "SHOW DOCUMENT" })).toBeVisible();
    await page.getByRole("button", { name: "SHOW DOCUMENT" }).click();
    await expect(page.getByText("Source document")).toBeVisible();
  });

  test("mobile: register/document toggle, citing jumps to the document", async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, "pane toggle only exists below lg");
    await page.goto("/workspace/1?role=security");
    await expect(page.getByRole("button", { name: "Register" })).toBeVisible();
    // document hidden while register is active
    await expect(page.getByText("Source document")).toBeHidden();
    await page.getByRole("button", { name: /View in document → p\.4/ }).first().click();
    await expect(page.getByText("Source document")).toBeVisible();
    await page.getByRole("button", { name: "Register" }).click();
    await expect(page.getByText(/\d+ obligations/)).toBeVisible();
  });

  test("citing an obligation makes the exact sentence glow (span-level highlight)", async ({
    page,
  }) => {
    await page.goto("/workspace/1?role=security");
    await page.getByRole("button", { name: /View in document → p\.4/ }).first().click();
    // react-pdf renders the text layer, and the cited sentence gets marked
    const glow = page.locator("mark.anvil-glow");
    await expect(glow.first()).toBeVisible({ timeout: 20_000 });
    const glowText = (await glow.allTextContents()).join(" ");
    expect(glowText).toContain("72 hours");
  });
});

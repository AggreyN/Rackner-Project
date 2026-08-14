import { test, expect } from "@playwright/test";
import { isDesktop, signIn } from "./helpers";

// The analysis workspace: compatibility score, cited obligations,
// click-to-cite highlight, spend history, contact + integrity flag, chat.

test.beforeEach(async ({ page }) => {
  await signIn(page);
  await page.goto("/opportunity/disa-soc-0042");
});

test.describe("compatibility", () => {
  test("renders the donut, verdict, and all 8 weighted factors", async ({ page }) => {
    await expect(page.getByTestId("fit-donut")).toBeVisible();
    await expect(page.getByTestId("fit-donut")).toContainText("82");
    await expect(page.getByText("Strong fit — recommend pursue")).toBeVisible();
    for (const factor of [
      "Strategic / mission alignment",
      "Technical & domain capability",
      "Past-performance relevance",
      "Contract-vehicle access",
      "Set-aside eligibility",
      "Incumbent advantage (inverse)",
      "Pricing / size fit",
      "Time to respond / shape",
    ]) {
      await expect(page.getByText(factor)).toBeVisible();
    }
  });
});

test.describe("obligations", () => {
  test("groups by time with verified citations, and can regroup by type", async ({ page }) => {
    await expect(page.getByTestId("obligation")).toHaveCount(4);
    await expect(page.getByRole("heading", { name: /^Immediate \(\d+\)$/ })).toBeVisible();
    await expect(page.getByText("✓ quote verified in source").first()).toBeVisible();
    await page.getByRole("button", { name: "By type" }).click();
    await expect(page.getByRole("heading", { name: /^Submission \(\d+\)$/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^Certification \(\d+\)$/ })).toBeVisible();
  });

  test("clicking a quote jumps the source pane and glows the exact sentence", async ({
    page,
  }, testInfo) => {
    await page
      .getByRole("button", { name: /Offers are due no later than 2:00 PM ET/ })
      .click();
    // Below lg the workspace flips to the Source tab; on desktop the pane is
    // already visible. Either way the cited sentence must glow.
    const highlight = page.getByTestId("cite-highlight");
    await expect(highlight).toBeVisible();
    await expect(highlight).toHaveText(
      "Offers are due no later than 2:00 PM ET on 30 August 2026 through the SAM.gov submission portal."
    );
    if (!isDesktop(testInfo)) {
      // and the mobile toggle should now be on Source doc
      await expect(page.getByRole("button", { name: "Source doc" })).toHaveClass(/border-b-2/);
    }
  });

  test("an unverified quote is flagged, not hidden", async ({ page }) => {
    await page.goto("/opportunity/af-devsecops-0107");
    await expect(page.getByText("⚠ quote not verified — treat with caution")).toBeVisible();
  });
});

test.describe("source pane", () => {
  test("desktop: collapses to a rail and expands back", async ({ page }, testInfo) => {
    test.skip(!isDesktop(testInfo), "collapse rail is a desktop affordance");
    await expect(page.getByText("SECTION C — DESCRIPTION / SPECIFICATIONS")).toBeVisible();
    await page.getByTestId("source-collapse").click();
    await expect(page.getByText("SECTION C — DESCRIPTION / SPECIFICATIONS")).toBeHidden();
    await page.getByTestId("source-expand").click();
    await expect(page.getByText("SECTION C — DESCRIPTION / SPECIFICATIONS")).toBeVisible();
  });

  test("small screens: pane toggle switches between analysis and source", async ({
    page,
  }, testInfo) => {
    test.skip(isDesktop(testInfo), "pane toggle only exists below lg");
    await expect(page.getByTestId("fit-donut")).toBeVisible();
    await page.getByRole("button", { name: "Source doc" }).click();
    await expect(page.getByText("SECTION C — DESCRIPTION / SPECIFICATIONS")).toBeVisible();
    await expect(page.getByTestId("fit-donut")).toBeHidden();
    await page.getByRole("button", { name: "Analysis", exact: true }).click();
    await expect(page.getByTestId("fit-donut")).toBeVisible();
  });
});

test.describe("money and contact", () => {
  test("spend panel shows USAspending history and incumbent", async ({ page }) => {
    const spend = page.getByTestId("spend-panel");
    await expect(spend).toBeVisible();
    await expect(spend).toContainText("$9.7M");
    await expect(spend).toContainText("SmallCyber LLC · UEI ABC123XYZ");
    await expect(spend).toContainText("↑ growing ~24%/yr");
  });

  test("no-history opportunity says so instead of an empty chart", async ({ page }) => {
    await page.goto("/opportunity/af-devsecops-0107");
    await expect(page.getByTestId("spend-panel")).toContainText(
      "No prior award history found"
    );
  });

  test("contact card shows the discovered email, confidence, and integrity flag", async ({
    page,
  }) => {
    const contact = page.getByTestId("contact-panel");
    await expect(contact).toContainText("Janet Morales");
    await expect(contact).toContainText("janet.morales@disa.mil");
    await expect(contact).toContainText("92% verified");
    await expect(page.getByTestId("integrity-flag")).toContainText("Procurement Integrity");
  });
});

test.describe("assistant", () => {
  test("answers with citations that jump to the source", async ({ page }, testInfo) => {
    await page
      .getByPlaceholder("Ask Anvil Anything about this contract…")
      .fill("What would disqualify us from bidding?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText(/CMMC Level 2 is required at award/)).toBeVisible();
    await page.getByTestId("chat-panel").getByRole("button", { name: /§M\.4/ }).click();
    if (isDesktop(testInfo)) {
      await expect(page.getByText("SECTION M — EVALUATION")).toBeVisible();
    } else {
      await expect(page.getByText("SECTION M — EVALUATION")).toBeVisible();
      await expect(page.getByTestId("chat-panel")).toBeHidden();
    }
  });
});

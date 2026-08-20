import { test, expect, type Page } from "@playwright/test";

// New feature pass: floating Anvil window (bottom-left launcher, drag,
// resize, shared transcript), PDF import → analysis, per-user bookmarks +
// saved drawer, and neutral (unscored) mode when no lifecycle plan is on
// file.

async function signIn(page: Page, email = "remy@rackner.com") {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill("demo-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Find your next opportunity" })).toBeVisible();
}

async function openDisa(page: Page) {
  await signIn(page);
  await page.getByTestId("opportunity-card").filter({ hasText: "Managed Cybersecurity" }).click();
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 20_000 });
}

// A minimal but valid-enough PDF payload for the import input.
const FAKE_PDF = {
  name: "Sub-Contract_Cyber-Support.pdf",
  mimeType: "application/pdf",
  buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"),
};

// ---------- floating Anvil window ----------

test("launcher sits bottom-left and opens the floating chat", async ({ page }) => {
  await openDisa(page);

  const launcher = page.getByTestId("anvil-launcher");
  await expect(launcher).toBeVisible();
  const box = (await launcher.boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(box.x).toBeLessThan(viewport.width / 4); // left side
  expect(box.y).toBeGreaterThan(viewport.height / 2); // bottom half

  await launcher.click();
  await expect(page.getByTestId("floating-window")).toBeVisible();
  // Launcher hides while open; close brings it back.
  await expect(launcher).toBeHidden();
  await page.getByTestId("floating-window-close").click();
  await expect(page.getByTestId("floating-window")).toBeHidden();
  await expect(launcher).toBeVisible();
});

test("floating window and inline panel share one transcript", async ({ page }) => {
  await openDisa(page);
  await page.getByTestId("anvil-launcher").click();

  const win = page.getByTestId("floating-window");
  await win.getByPlaceholder(/Ask Anvil/i).fill("When is it due?");
  await win.getByRole("button", { name: "Send" }).click();
  await expect(win.getByText(/30 August 2026/)).toBeVisible({ timeout: 15_000 });

  // Same conversation appears in the inline panel below the obligations.
  await page.getByTestId("floating-window-close").click();
  const inline = page.getByTestId("chat-panel");
  await expect(inline.getByText("When is it due?")).toBeVisible();
  await expect(inline.getByText(/30 August 2026/)).toBeVisible();
});

test("the window drags and resizes", async ({ page, isMobile }) => {
  test.skip(isMobile, "drag/resize is a desktop interaction");
  await openDisa(page);
  await page.getByTestId("anvil-launcher").click();

  const win = page.getByTestId("floating-window");
  const before = (await win.boundingBox())!;

  // Drag by the header.
  const header = page.getByTestId("floating-window-header");
  const hb = (await header.boundingBox())!;
  await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
  await page.mouse.down();
  await page.mouse.move(hb.x + hb.width / 2 + 140, hb.y + hb.height / 2 - 120, { steps: 8 });
  await page.mouse.up();
  const afterDrag = (await win.boundingBox())!;
  expect(Math.round(afterDrag.x - before.x)).toBeGreaterThan(100);
  expect(Math.round(before.y - afterDrag.y)).toBeGreaterThan(80);

  // Resize by the grip.
  const grip = page.getByTestId("floating-window-resize");
  const gb = (await grip.boundingBox())!;
  await page.mouse.move(gb.x + gb.width / 2, gb.y + gb.height / 2);
  await page.mouse.down();
  await page.mouse.move(gb.x + 90, gb.y + 70, { steps: 6 });
  await page.mouse.up();
  const afterResize = (await win.boundingBox())!;
  expect(afterResize.width).toBeGreaterThan(afterDrag.width + 60);
  expect(afterResize.height).toBeGreaterThan(afterDrag.height + 40);
});

test("citations from the floating window still ground into the source", async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, "source pane is behind a tab on mobile; covered inline there");
  await openDisa(page);
  await page.getByTestId("anvil-launcher").click();

  const win = page.getByTestId("floating-window");
  await win.getByPlaceholder(/Ask Anvil/i).fill("What would disqualify us?");
  await win.getByRole("button", { name: "Send" }).click();
  await win.getByRole("button", { name: "§M.4" }).click();

  await expect(page.getByTestId("cite-highlight")).toBeVisible();
  await expect(page.getByTestId("cite-highlight")).toContainText("CMMC Level 2");
});

// ---------- PDF import ----------

test("importing a PDF analyzes it like any opportunity", async ({ page }) => {
  await signIn(page);
  await page.getByTestId("import-pdf").click();
  await page.locator('input[type="file"]').setInputFiles(FAKE_PDF);

  // Lands in the workspace with a scored analysis + cited obligations.
  await expect(page).toHaveURL(/\/opportunity\/imported-/, { timeout: 20_000 });
  await expect(page.getByRole("heading", { name: /Sub Contract Cyber Support/i })).toBeVisible();
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("obligation").first()).toBeVisible();
});

test("imported documents get the same click-to-cite grounding", async ({ page, isMobile }) => {
  await signIn(page);
  await page.getByTestId("import-pdf").click();
  await page.locator('input[type="file"]').setInputFiles(FAKE_PDF);
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 20_000 });

  await page
    .getByTitle("View in the source document")
    .filter({ hasText: "monthly progress report" })
    .click();
  if (isMobile) {
    // cite flips the mobile pane to the source automatically
  }
  await expect(page.getByTestId("cite-highlight")).toBeVisible();
  await expect(page.getByTestId("cite-highlight")).toContainText("monthly progress report");
});

// ---------- bookmarks & saved drawer ----------

test("starring a card saves it; the drawer lists and opens it", async ({ page }) => {
  await signIn(page);
  await expect(page.getByTestId("saved-tab")).toContainText("0");

  const card = page.getByTestId("opportunity-card").filter({ hasText: "Managed Cybersecurity" });
  await card.getByTestId("bookmark-star").click();
  // Starring must not navigate — the card is a link.
  await expect(page.getByRole("heading", { name: "Find your next opportunity" })).toBeVisible();
  await expect(page.getByTestId("saved-tab")).toContainText("1");

  await page.getByTestId("saved-tab").click();
  const drawer = page.getByTestId("saved-drawer");
  await expect(drawer).toBeVisible();
  const item = page.getByTestId("saved-item").filter({ hasText: "Managed Cybersecurity" });
  await expect(item).toBeVisible();

  await item.click();
  await expect(page).toHaveURL(/\/opportunity\/disa-soc-0042/);
  await expect(page.getByTestId("fit-donut")).toBeVisible({ timeout: 20_000 });
});

test("unstarring from the drawer removes it", async ({ page }) => {
  await signIn(page);
  await page
    .getByTestId("opportunity-card")
    .filter({ hasText: "Managed Cybersecurity" })
    .getByTestId("bookmark-star")
    .click();
  await page.getByTestId("saved-tab").click();
  await page.getByTestId("saved-item").getByTestId("bookmark-star").click();
  await expect(page.getByTestId("saved-item")).toHaveCount(0);
  await expect(page.getByTestId("saved-drawer")).toContainText("Nothing saved yet");
});

test("bookmarks are per user", async ({ page }) => {
  await signIn(page, "remy@rackner.com");
  await page
    .getByTestId("opportunity-card")
    .filter({ hasText: "Managed Cybersecurity" })
    .getByTestId("bookmark-star")
    .click();
  await expect(page.getByTestId("saved-tab")).toContainText("1");

  // Sign out, sign in as someone else — their list is empty.
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "kaliza@rackner.com");
  await expect(page.getByTestId("saved-tab")).toContainText("0");

  // And Remy's save is still there when he returns.
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "remy@rackner.com");
  await expect(page.getByTestId("saved-tab")).toContainText("1");
});

// ---------- neutral mode (no lifecycle plan) ----------

test("removing the lifecycle plan makes search and suggestions unscored", async ({ page }) => {
  await signIn(page);

  // Suggested is scored while the plan is on file.
  await expect(
    page.getByTestId("opportunity-card").filter({ hasText: "Managed Cybersecurity" })
  ).toContainText("82");

  // Remove the plan. Removal is destructive (analyses reset), so it asks
  // first — Playwright dismisses dialogs by default, which would silently
  // no-op the whole test.
  await page.getByRole("button", { name: /Lifecycle plan on file/ }).click();
  page.once("dialog", (d) => d.accept());
  await page.getByTestId("remove-plan").click();
  await expect(page.getByRole("button", { name: "Add lifecycle plan" })).toBeVisible();

  // Suggestions re-rank neutrally: no fit numbers, dash badges instead.
  await expect(page.getByText("Add your lifecycle plan to rank these by fit")).toBeVisible();
  await expect(
    page.getByTestId("opportunity-card").filter({ hasText: "Managed Cybersecurity" })
  ).not.toContainText("82");

  // Search is neutral too, and says so.
  await page.getByPlaceholder(/Search by keyword/).fill("cyber");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByTestId("results")).toHaveAttribute("data-busy", "false");
  await expect(page.getByTestId("neutral-note")).toBeVisible();
  const cardText = await page.getByTestId("opportunity-card").allInnerTexts();
  expect(cardText.join(" ")).not.toMatch(/\b(82|74|79)\b/);
});

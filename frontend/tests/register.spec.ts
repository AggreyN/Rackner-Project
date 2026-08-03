import { test, expect } from "@playwright/test";

// Week-5 behaviors: status tracking with live counts, CSV export,
// and the review state surviving a reload (mock persists to localStorage).

test.describe("status tracking", () => {
  test("cycling a status chip updates the header counts and persists", async ({ page }) => {
    await page.goto("/workspace/1?role=contracts");
    await expect(page.getByText(/0 done/)).toBeVisible();

    const chip = page.getByRole("button", { name: "open", exact: true }).first();
    await chip.click(); // open → in-review
    await expect(page.getByText(/1 in review/)).toBeVisible();
    await page.getByRole("button", { name: "in-review", exact: true }).first().click(); // → done
    await expect(page.getByText(/1 done/)).toBeVisible();

    // Survives a reload — the register is a living document, not a one-shot.
    // (wait for the mock backend's write to land before reloading)
    await page.waitForFunction(() =>
      localStorage.getItem("anvil-obligation-status")?.includes('"done"')
    );
    await page.reload();
    await expect(page.getByText(/1 done/)).toBeVisible();

    // Clean up back to open for other tests.
    await page.getByRole("button", { name: "done", exact: true }).first().click();
    await expect(page.getByText(/0 done/)).toBeVisible();
  });
});

test.describe("CSV export", () => {
  test("downloads the register with citations", async ({ page }) => {
    await page.goto("/workspace/1?role=security");
    await expect(page.getByText(/\d+ obligations/)).toBeVisible();

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export CSV" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/obligation-register-.*\.csv/);

    const path = await download.path();
    const fs = await import("node:fs/promises");
    const body = await fs.readFile(path, "utf8");
    expect(body).toContain("Verbatim quote");
    expect(body).toContain("The Contractor shall rapidly report cyber incidents");
    expect(body).toContain("NO — flagged"); // unverified quotes are visibly flagged in exports too
  });
});

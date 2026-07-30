import type { Page, TestInfo } from "@playwright/test";

// Seed a signed-in session before any page script runs — the mock backend
// issues tokens shaped like this, and useRequireAuth only checks presence.
export async function signIn(page: Page, email = "remy@rackner.com"): Promise<void> {
  await page.addInitScript(
    ([e]) => {
      sessionStorage.setItem("fdi_token", `mock-jwt-${btoa(e)}`);
      sessionStorage.setItem("fdi_email", e);
    },
    [email]
  );
}

/** The split pane goes side-by-side at Tailwind's lg breakpoint (1024px).
 *  Below that (tablet portrait + mobile) the workspace uses the pane toggle. */
export function isDesktop(testInfo: TestInfo): boolean {
  return testInfo.project.name === "desktop";
}

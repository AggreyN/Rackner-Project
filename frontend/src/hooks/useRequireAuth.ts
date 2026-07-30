"use client";

// Redirects to /login when no session token is present. Sign-in is step 1
// of the FDI flow (build plan §1) — every page except /login requires it.
// Session state is read via useSyncExternalStore (sessionStorage is an
// external system), so there's no setState-in-effect cascade.

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { getEmail, isSignedIn } from "@/lib/auth";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

/** null → not signed in; string → the signed-in email ("" if unknown). */
function getSnapshot(): string | null {
  return isSignedIn() ? (getEmail() ?? "") : null;
}

export function useRequireAuth(): { ready: boolean; email: string } {
  const router = useRouter();
  const session = useSyncExternalStore(subscribe, getSnapshot, () => null);

  useEffect(() => {
    // Re-check storage directly: during hydration the rendered snapshot is
    // still the server's null, and redirecting on that would bounce
    // signed-in users off deep links.
    if (!isSignedIn()) router.replace("/login");
  }, [session, router]);

  return { ready: session !== null, email: session ?? "" };
}

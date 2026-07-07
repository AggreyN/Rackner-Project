"use client";

// Renders nothing while the auth flag is off — the demo stays frictionless.

import { useRouter } from "next/navigation";
import { clearToken, getToken, isAuthEnabled } from "@/lib/auth";

export default function SignOutButton() {
  const router = useRouter();
  if (!isAuthEnabled() || !getToken()) return null;
  return (
    <button
      onClick={() => {
        clearToken();
        router.replace("/login");
      }}
      className="text-xs text-[#51606f] underline underline-offset-2 hover:text-[#16324f]"
    >
      Sign out
    </button>
  );
}

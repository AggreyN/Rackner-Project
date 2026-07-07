"use client";

// Gate a page behind the auth flag. No-op while auth is disabled.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken, isAuthEnabled } from "@/lib/auth";

export function useRequireAuth() {
  const router = useRouter();
  useEffect(() => {
    if (isAuthEnabled() && !getToken()) router.replace("/login");
  }, [router]);
}

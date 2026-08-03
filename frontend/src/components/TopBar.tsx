"use client";

// Sticky app header: brand, lifecycle-plan chip (opens the profile modal),
// org label, avatar with sign-out. Flat navy/white per the design system.

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearSession } from "@/lib/auth";
import type { Profile } from "@/lib/types";
import LifecycleModal from "./LifecycleModal";

interface Props {
  profile: Profile | null;
  onLifecycleUpdated?: () => void;
}

export default function TopBar({ profile, onLifecycleUpdated }: Props) {
  const router = useRouter();
  const [showPlan, setShowPlan] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const hasPlan = !!profile?.lifecycle;

  return (
    <header className="sticky top-0 z-20 border-b border-[#d7dee6] bg-white">
      <div className="flex items-center justify-between px-4 py-2.5 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5 font-bold text-[#16324f]">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[#16324f] text-sm text-white">
            ◆
          </span>
          <span className="text-[15px]">
            Rackner FDI
            <span className="ml-2 hidden text-xs font-normal text-[#51606f] md:inline">
              Federal Document Intelligence
            </span>
          </span>
        </Link>

        <div className="flex items-center gap-3 text-xs text-[#51606f]">
          <button
            onClick={() => setShowPlan(true)}
            className={
              "rounded-full border px-3 py-1 " +
              (hasPlan
                ? "border-[#bfe0cd] text-[#1e7a46] hover:bg-[#f0f7f3]"
                : "border-[#eeddba] bg-[#fbf4e6] text-[#9a6a1e] hover:bg-[#f6ecd6]")
            }
          >
            {hasPlan ? "✓ Lifecycle plan on file" : "Add lifecycle plan"}
          </button>
          <span className="hidden sm:inline">{profile?.user.org ?? "rackner.com"}</span>
          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label="Account menu"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-[#16324f] text-xs font-bold text-white"
            >
              {profile?.user.initials ?? "·"}
            </button>
            {menuOpen && (
              <div className="absolute right-0 mt-2 w-44 border border-[#d7dee6] bg-white py-1 shadow-sm">
                <div className="truncate px-3 py-1.5 text-xs text-[#51606f]">
                  {profile?.user.email}
                </div>
                <button
                  onClick={() => {
                    clearSession();
                    router.replace("/login");
                  }}
                  className="w-full px-3 py-1.5 text-left text-sm text-[#16324f] hover:bg-[#f5f7f9]"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {showPlan && (
        <LifecycleModal
          lifecycle={profile?.lifecycle ?? null}
          onClose={() => setShowPlan(false)}
          onUpdated={() => {
            setShowPlan(false);
            onLifecycleUpdated?.();
          }}
        />
      )}
    </header>
  );
}
